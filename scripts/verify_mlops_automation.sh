#!/usr/bin/env bash
# Local evidence, isolated from the running registry and deployed model.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_dir="$PWD"
export PYTHONPATH="$repo_dir/src"
uv_bin="${UV_BIN:-uv}"
uv_executable="$(command -v "$uv_bin")"
export PATH="$(dirname "$uv_executable"):$PATH"
mkdir -p artifacts
audit_dir="$(mktemp -d "$repo_dir/artifacts/automation-local-XXXXXX")"
export MLFLOW_TRACKING_URI="sqlite:///$audit_dir/mlflow.db"
echo "Audit directory: $audit_dir"
"$uv_bin" run --frozen --extra dev pytest | tee "$audit_dir/tests.log"

# Publish the existing cached version into an isolated filesystem remote,
# switch to an empty cache, then pull it. No changes to user's DVC config.
mkdir -p "$audit_dir/checkout/data/raw"
git -C "$audit_dir/checkout" init -q
cp data/raw/open_meteo_history.dvc "$audit_dir/checkout/data/raw/"
(cd "$audit_dir/checkout"
 "$repo_dir/.venv/bin/dvc" init -q
 "$repo_dir/.venv/bin/dvc" config --local cache.dir "$repo_dir/.dvc/cache"
 "$repo_dir/.venv/bin/dvc" remote add --local -d verification "$audit_dir/dvc-remote"
 "$repo_dir/.venv/bin/dvc" push data/raw/open_meteo_history.dvc
 "$repo_dir/.venv/bin/dvc" config --local cache.dir "$audit_dir/empty-cache"
 "$repo_dir/.venv/bin/dvc" pull data/raw/open_meteo_history.dvc
) 2>&1 | tee "$audit_dir/dvc.log"

export MLFLOW_LOCAL_AUDIT_DIR="$audit_dir"
"$repo_dir/.venv/bin/python" - <<'PY'
import os
from pathlib import Path
import mlflow
mlflow.create_experiment(
    "rain-risk-code-trigger",
    artifact_location=(Path(os.environ["MLFLOW_LOCAL_AUDIT_DIR"]) / "mlartifacts").as_uri(),
)
PY

"$uv_bin" run --frozen --extra dev python src/data/preprocess.py \
 --raw-dir "$audit_dir/checkout/data/raw/open_meteo_history" \
 --processed-dir "$audit_dir/processed" --quarantine-dir "$audit_dir/quarantine" \
 | tee "$audit_dir/preprocess.log"
"$uv_bin" run --frozen --extra dev python -m rain_prediction.training.automated_train \
 --processed-dir "$audit_dir/processed" --output "$audit_dir/run.json" \
 | tee "$audit_dir/train.log"
"$uv_bin" run --frozen --extra dev python -m rain_prediction.training.evaluate_and_register \
 --run-reference "$audit_dir/run.json" --report "$audit_dir/evaluation.json" \
 --tracking-uri "$MLFLOW_TRACKING_URI" --source-commit "$(git rev-parse HEAD)-working-tree" \
 --model-name rain-risk-classifier-ci-local --register \
 | tee "$audit_dir/registry.log"
echo "Local verification complete: $audit_dir/evaluation.json"
echo 'This is local evidence; a successful GitHub Actions URL still requires remote configuration.'
