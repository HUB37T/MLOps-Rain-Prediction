"""Fail-closed validation of one exact run; optional Staging registration."""
from __future__ import annotations

import argparse
import json
import math
from io import StringIO
from pathlib import Path


def validation_errors(metrics: dict, policy: dict) -> list[str]:
    errors = []
    for metric, key in (
        ("validation_pr_auc", "minimum_validation_pr_auc"),
        ("validation_f1", "minimum_validation_f1"),
    ):
        threshold = policy.get(key)
        value = metrics.get(metric)
        if (isinstance(threshold, bool) or not isinstance(threshold, (float, int))
                or not math.isfinite(threshold) or not 0 <= threshold <= 1):
            errors.append(f"Invalid policy: {key}")
        elif (isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or not 0 <= value <= 1):
            errors.append(f"Missing or invalid metric: {metric}")
        elif value < threshold:
            errors.append(f"{metric}={value:.6f} < {threshold:.6f}")
    return errors


def evaluate(reference, policy, report_path, tracking_uri, source_commit,
             register=False, model_name="rain-risk-classifier-ci", client=None):
    import mlflow
    import pandas as pd
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(tracking_uri)
    client = client or MlflowClient(tracking_uri=tracking_uri)
    report = {"run_id": reference["run_id"], "model_uri": reference.get("model_uri"),
              "source_commit": source_commit,
              "passed": False, "registered": False, "errors": []}
    try:
        run = client.get_run(reference["run_id"])
        report["metrics"] = {
            key: value if math.isfinite(value) else None
            for key, value in run.data.metrics.items()
        }
        report["policy"] = policy
        report["errors"] = validation_errors(run.data.metrics, policy)
        if run.info.status != "FINISHED":
            report["errors"].append("Run is not FINISHED")
        if report["errors"]:
            raise ValueError("; ".join(report["errors"]))

        # Link both the model and dataset digest to the selected run.
        logged_model = mlflow.get_logged_model(reference["model_uri"].split("/")[-1])
        if logged_model.source_run_id != reference["run_id"]:
            raise ValueError("Model does not belong to selected run")
        digest = run.data.params.get("processed_file_sha256")
        if not digest or digest != reference.get("processed_file_sha256"):
            raise ValueError("Processed dataset digest mismatch")

        # Use the model's own logged input example, not arbitrary latest data.
        input_path = mlflow.artifacts.download_artifacts(
            artifact_uri=logged_model.artifact_location.rstrip("/") + "/input_example.json")
        sample = pd.read_json(StringIO(Path(input_path).read_text()), orient="split")
        # Preserve the float64 signature logged by train.py.
        sample = sample.astype("float64")
        model = mlflow.pyfunc.load_model(reference["model_uri"])
        import numpy as np
        predictions = np.asarray(model.predict(sample))
        if predictions.shape != (len(sample),) or not np.isin(predictions, [0, 1]).all():
            raise ValueError("Invalid inference smoke-test output")
        report["smoke_test_rows"] = len(sample)

        raw_pointer = Path("data/raw/open_meteo_history.dvc")
        import yaml
        pointer = yaml.safe_load(raw_pointer.read_text(encoding="utf-8"))
        logged_pointer_path = mlflow.artifacts.download_artifacts(
            run_id=reference["run_id"],
            artifact_path="data_version/open_meteo_history.dvc")
        logged_pointer = yaml.safe_load(Path(logged_pointer_path).read_text(encoding="utf-8"))
        if logged_pointer != pointer:
            raise ValueError("DVC dataset pointer differs from training run")
        report["data_lineage"] = {"raw_dvc": pointer,
                                  "processed_sha256": digest}
        for key, value in {"source_commit": source_commit,
                           "automation": "code-as-trigger",
                           "validation_status": "passed"}.items():
            client.set_tag(reference["run_id"], key, value)

        if register:
            # Safe retry: reuse the version for this run; don't duplicate it.
            versions = client.search_model_versions(f"name = '{model_name}'")
            matching = [v for v in versions if v.run_id == reference["run_id"]]
            version = (matching[0] if matching else mlflow.register_model(
                reference["model_uri"], model_name))
            client.transition_model_version_stage(
                name=model_name, version=version.version,
                stage="Staging", archive_existing_versions=False)
            client.set_model_version_tag(model_name, version.version,
                                         "source_commit", source_commit)
            client.set_model_version_tag(model_name, version.version,
                                         "validation_status", "passed")
            current = client.get_model_version(model_name, version.version)
            if current.current_stage != "Staging":
                raise ValueError("Registry did not confirm Staging")
            report.update(registered=True, model_name=model_name,
                          version=version.version, stage=current.current_stage)
        report["passed"] = True
        return report
    except Exception as exc:
        report["errors"].append(str(exc))
        raise
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False),
                               encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-reference", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("configs/automated-training.json"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/automation/evaluation.json"))
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--model-name", default="rain-risk-classifier-ci")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(
            json.loads(args.run_reference.read_text()), json.loads(args.policy.read_text()),
            args.report, args.tracking_uri, args.source_commit,
            register=args.register, model_name=args.model_name)
    except Exception as exc:
        raise SystemExit(f"MODEL VALIDATION FAILED: {exc}") from exc
    print("MODEL VALIDATION PASSED")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
