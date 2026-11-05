"""Real MLflow 3 logged-model URI -> smoke test -> confirmed Staging."""
import json
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import RandomForestClassifier

from rain_prediction.training.evaluate_and_register import evaluate


def test_accepted_logged_model_can_be_loaded_and_registered(tmp_path):
    previous_uri = mlflow.get_tracking_uri()
    uri = "sqlite:///" + str(tmp_path / "registry.db")
    try:
        mlflow.set_tracking_uri(uri)
        mlflow.create_experiment("registry-regression", (tmp_path / "models").as_uri())
        mlflow.set_experiment("registry-regression")
        features = pd.DataFrame({"humidity": [20.0, 95.0, 30.0, 90.0]})
        estimator = RandomForestClassifier(n_estimators=2, random_state=42).fit(
            features, [0, 1, 0, 1])
        with mlflow.start_run() as run:
            mlflow.log_param("processed_file_sha256", "fixture-digest")
            mlflow.log_metrics({"validation_pr_auc": 0.95, "validation_f1": 0.85})
            mlflow.log_artifact("data/raw/open_meteo_history.dvc", "data_version")
            info = mlflow.sklearn.log_model(
                estimator, name="model", input_example=features,
                signature=infer_signature(features, estimator.predict(features)),
                pip_requirements=[])
        reference = {"run_id": run.info.run_id, "model_uri": info.model_uri,
                     "processed_file_sha256": "fixture-digest"}
        report = evaluate(reference,
                          {"minimum_validation_pr_auc": 0.9, "minimum_validation_f1": 0.82},
                          tmp_path / "evaluation.json", uri, "fixture-sha",
                          register=True, model_name="registry-regression")
        assert report["passed"] is True
        assert report["registered"] is True
        assert report["stage"] == "Staging"
        assert report["smoke_test_rows"] == 4
        assert json.loads((tmp_path / "evaluation.json").read_text())["source_commit"] == "fixture-sha"
    finally:
        mlflow.set_tracking_uri(previous_uri)
