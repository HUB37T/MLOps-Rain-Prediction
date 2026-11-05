"""Initialize a persistent CI registry with a stable artifact mount path."""
from pathlib import Path

import mlflow


def main():
    state = Path("/mlops-state/registry")
    state.mkdir(parents=True, exist_ok=True)
    Path("artifacts/automation").mkdir(parents=True, exist_ok=True)
    name = "rain-risk-code-trigger"
    experiment = mlflow.get_experiment_by_name(name)
    location = (state / "artifacts").as_uri()
    if experiment is None:
        mlflow.create_experiment(name, artifact_location=location)
    elif experiment.artifact_location != location:
        raise SystemExit("CI experiment has an unexpected artifact location")
    print("Persistent local MLflow Registry ready")


if __name__ == "__main__":
    main()
