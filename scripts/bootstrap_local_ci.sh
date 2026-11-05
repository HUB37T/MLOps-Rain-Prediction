#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
repo_dir="$PWD"
uv_bin="${UV_BIN:-/home/attacker/.local/bin/uv}"
dvc_cmd=("$uv_bin" tool run --from dvc==3.67.1 dvc)
state_dir="${1:?Pass an absolute directory for local CI state}"
[[ "$state_dir" = /* ]] || { echo 'State directory must be absolute'; exit 1; }
mkdir -p "$state_dir/dvc" "$state_dir/registry" "$state_dir/uv-cache"
bootstrap_dir="$(mktemp -d "$state_dir/bootstrap-XXXXXX")"
mkdir -p "$bootstrap_dir/data/raw"
cp data/raw/open_meteo_history.dvc "$bootstrap_dir/data/raw/"
git -C "$bootstrap_dir" init -q
cd "$bootstrap_dir"
"${dvc_cmd[@]}" init -q
"${dvc_cmd[@]}" config --local cache.dir "$repo_dir/.dvc/cache"
"${dvc_cmd[@]}" remote add --local -d laptop "$state_dir/dvc"
"${dvc_cmd[@]}" push data/raw/open_meteo_history.dvc
echo "Local DVC remote prepared: $state_dir/dvc"
