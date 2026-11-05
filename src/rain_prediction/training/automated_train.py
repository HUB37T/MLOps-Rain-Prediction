"""Run the existing trainer with reviewed, versioned hyperparameters."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/automated-training.json"))
    parser.add_argument("--processed-dir", default="artifacts/automation/processed")
    parser.add_argument("--output", default="artifacts/automation/run.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    command = [sys.executable, "-m", "rain_prediction.training.train",
               "--run-name", "automated-rf-" + os.getenv("GITHUB_SHA", "local")[:12],
               "--experiment-name", "rain-risk-code-trigger",
               "--processed-dir", args.processed_dir,
               "--run-output", args.output]
    for key in ("model", "class_weight", "n_estimators", "max_depth",
                "min_samples_leaf", "max_features", "random_state"):
        command.extend(["--" + key.replace("_", "-"), str(config[key])])
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
