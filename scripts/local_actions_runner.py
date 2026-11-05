"""Windows/WSL runner management; no account beyond the existing GitHub account.

Usage: python scripts/local_actions_runner.py prepare|start|status|ui
The runner is ephemeral: use start again for the next GitHub job.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.request


REPO = Path(__file__).resolve().parents[1]
SLUG = "HUB37T/MLOps-Rain-Prediction"
IMAGE = "rain-lk08-actions-runner:local"
CONTAINER = "rain-lk08-runner"
STATE = "/home/attacker/.local/share/rain-mlops-ci"


def linux(*args, **kwargs):
    return subprocess.run(["wsl.exe", "--exec", *args], check=True, **kwargs)


def docker(*args, **kwargs):
    return linux("docker", *args, **kwargs)


def api(path, post=False):
    # Credential stays in memory, is never echoed, written to disk or sent to runner.
    credential = subprocess.run(
        ["git", "-C", str(REPO), "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True,
        env=dict(os.environ, GCM_INTERACTIVE="Never", GIT_TERMINAL_PROMPT="0"),
        timeout=20, check=True,
    )
    fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    token = fields.get("password")
    if not token:
        raise SystemExit("Login to GitHub using Git Credential Manager first.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{SLUG}/{path}",
        data=b"{}" if post else None,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json", "User-Agent": "rain-local-ci"},
        method="POST" if post else "GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def mounts():
    return ["--mount", f"type=bind,source={STATE}/registry,target=/mlops-state/registry",
            "--mount", f"type=bind,source={STATE}/uv-cache,target=/mlops-state/uv-cache",
            "--mount", f"type=bind,source={STATE}/dvc,target=/dvc-remote,readonly"]


def prepare():
    repo_linux = linux("wslpath", "-u", str(REPO), capture_output=True, text=True).stdout.strip()
    packages = api("actions/runners/downloads")
    package = next(p for p in packages if p["os"] == "linux" and p["architecture"] == "x64")
    docker("build", "-t", IMAGE, "--build-arg", "RUNNER_URL=" + package["download_url"],
           "--build-arg", "RUNNER_SHA256=" + package["sha256_checksum"],
           "-f", repo_linux + "/infrastructure/docker/actions-runner.Dockerfile", repo_linux)
    linux("bash", repo_linux + "/scripts/bootstrap_local_ci.sh", STATE)


def start():
    registered = api("actions/runners/registration-token", post=True)["token"]
    docker("run", "-d", "--rm", "--name", CONTAINER,
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "1024", "--cpus", "4", "--memory", "6g",
           *mounts(), IMAGE)
    command = (
        'read -r runner_token; ./config.sh --unattended '
        f'--url https://github.com/{SLUG} --token "$runner_token" '
        '--name rain-lk08-laptop --replace --labels rain-lk08 --ephemeral --disableupdate '
        '--work _work; result=$?; unset runner_token; '
        'if [ "$result" -eq 0 ]; then touch .configured; fi; exit "$result"'
    )
    try:
        docker("exec", "-i", CONTAINER, "bash", "-c", command,
               input=(registered + "\n").encode("utf-8"))
    except Exception:
        docker("stop", CONTAINER)
        raise
    print("Ephemeral runner started. It exits after one training job.")


def show_ui():
    docker("run", "-d", "--rm", "--name", "rain-lk08-mlflow-ui",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "-p", "127.0.0.1:5002:5000", *mounts(),
           "-e", "UV_CACHE_DIR=/mlops-state/uv-cache", IMAGE,
           "uv", "run", "--no-project", "--with", "mlflow==3.17.0", "mlflow", "server",
           "--backend-store-uri", "sqlite:////mlops-state/registry/mlflow.db",
           "--host", "0.0.0.0", "--port", "5000")
    print("MLflow CI UI: http://127.0.0.1:5002")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "start", "status", "ui"])
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "start":
        start()
    elif args.command == "ui":
        show_ui()
    else:
        print(json.dumps([{k: r[k] for k in ("name", "status", "busy")}
                          for r in api("actions/runners")["runners"]], indent=2))


if __name__ == "__main__":
    main()
