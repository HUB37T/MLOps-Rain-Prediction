"""Freeze the unique Production version and its real example for LK-10 serving.

Requires MLFLOW_TRACKING_URI pointing at the registry used in LK-07.
Does not register, train, promote, or change a model.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import mlflow
from mlflow import MlflowClient
import pandas as pd


def select_production(versions):
    ready = [v for v in versions if v.current_stage == "Production" and v.status == "READY"]
    if len(ready) != 1:
        raise ValueError(f"Expected exactly one READY Production version; found {len(ready)}")
    return ready[0]


def make_payload(frame: pd.DataFrame, feature_names: list[str]) -> dict:
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("Model signature must contain unique named features")
    if frame.empty or not set(feature_names).issubset(frame.columns):
        raise ValueError("Saved input example does not contain every model feature")
    selected = frame.loc[:, feature_names].head(2).astype("float64")
    # json.dumps below rejects NaN/Infinity rather than generating invalid JSON.
    result = {"dataframe_split": {"columns": feature_names, "data": selected.values.tolist()}}
    json.dumps(result, allow_nan=False)
    return result


def artifact_digest(directory: Path) -> str:
    """Fingerprint both relative filenames and bytes of the complete frozen model."""
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-name", default="rain-risk-classifier")
    parser.add_argument("--output", type=Path, default=Path("artifacts/model-serving"))
    args = parser.parse_args()
    if (args.output / "release.json").exists() or (args.output / "model").exists():
        raise SystemExit("Output already contains a release. Choose a new --output directory.")
    if "'" in args.model_name:
        raise SystemExit("Model name cannot contain a single quote")

    client = MlflowClient()
    versions = client.search_model_versions(f"name = '{args.model_name}'")
    version = select_production(versions)
    uri = f"models:/{args.model_name}/{version.version}"
    args.output.mkdir(parents=True, exist_ok=True)
    downloaded = Path(mlflow.artifacts.download_artifacts(artifact_uri=uri))
    local = args.output / "model"
    shutil.copytree(downloaded, local)
    model = mlflow.models.Model.load(str(local / "MLmodel"))
    if model.signature is None or model.signature.inputs is None:
        raise ValueError("Production model has no input signature")
    names = model.signature.inputs.input_names()
    example = model.load_input_example(str(local))
    if not isinstance(example, pd.DataFrame):
        raise ValueError("This weather model requires a saved DataFrame input example")
    payload = make_payload(example, names)
    predictor = mlflow.pyfunc.load_model(str(local))
    # The registered sklearn model returns class labels through PyFunc predict.
    expected = predictor.predict(pd.DataFrame(**payload["dataframe_split"]))
    if hasattr(expected, "tolist"):
        expected = expected.tolist()
    output = {"predictions": expected}
    metadata = model.metadata or {}
    release = {
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "tracking_uri": mlflow.get_tracking_uri(),
        "model_name": args.model_name, "version": str(version.version),
        "stage_at_export": version.current_stage, "run_id": version.run_id,
        "model_uri": uri, "source": version.source,
        "artifact_sha256": artifact_digest(local),
        "feature_count": len(names), "feature_columns": names,
        "decision_threshold": metadata.get("decision_threshold"),
        "response_semantics": "Registered sklearn predict class labels; not rain probabilities",
    }
    for filename, content in (("request.json", payload), ("expected.json", output),
                              ("release.json", release)):
        (args.output / filename).write_text(
            json.dumps(content, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(release, indent=2))
    print(f"Frozen model: {local}; real input: {args.output / 'request.json'}")


if __name__ == "__main__":
    main()
