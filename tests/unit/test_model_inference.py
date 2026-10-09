from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from rain_prediction.inference.model import (
    ModelInputError,
    RainModelPredictor,
)


def create_test_artifact(directory: Path) -> Path:
    artifact_directory = directory / "test-model"
    artifact_directory.mkdir()

    features = ["temperature", "humidity"]

    training_features = pd.DataFrame(
        {
            "temperature": [20.0, 22.0, 28.0, 30.0],
            "humidity": [50.0, 60.0, 85.0, 95.0],
        }
    )
    targets = [0, 0, 1, 1]

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    random_state=42
                ),
            ),
        ]
    )
    model.fit(training_features, targets)

    bundle = {
        "model": model,
        "feature_columns": features,
        "decision_threshold": 0.4,
        "target_column": "target_rain_next_3h",
        "feature_schema_version": "test-features-v1",
    }

    metadata = {
        "model_type": "logistic_regression",
        "run_id": "test-model-v1",
        "feature_schema_version": "test-features-v1",
        "test_period": "2025-10-01 through 2026-09-30",
    }

    joblib.dump(
        bundle,
        artifact_directory / "model.joblib",
    )
    (
        artifact_directory / "metadata.json"
    ).write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    return artifact_directory


def test_predict_returns_valid_rain_prediction(
    tmp_path: Path,
) -> None:
    artifact_directory = create_test_artifact(tmp_path)
    predictor = RainModelPredictor(artifact_directory)

    result = predictor.predict(
        {
            "temperature": 29.0,
            "humidity": 90.0,
        }
    )

    assert 0 <= result.probability <= 1
    assert result.predicted_class in {
        "rain",
        "no_rain",
    }
    assert result.decision_threshold == 0.4
    assert result.model_version == "test-model-v1"
    assert result.feature_schema_version == (
        "test-features-v1"
    )


def test_predict_rejects_missing_feature(
    tmp_path: Path,
) -> None:
    artifact_directory = create_test_artifact(tmp_path)
    predictor = RainModelPredictor(artifact_directory)

    with pytest.raises(
        ModelInputError,
        match="Fitur tidak lengkap",
    ):
        predictor.predict(
            {
                "temperature": 29.0,
            }
        )


def test_predict_rejects_non_finite_feature(
    tmp_path: Path,
) -> None:
    artifact_directory = create_test_artifact(tmp_path)
    predictor = RainModelPredictor(artifact_directory)

    with pytest.raises(
        ModelInputError,
        match="tidak finite",
    ):
        predictor.predict(
            {
                "temperature": float("nan"),
                "humidity": 90.0,
            }
        )