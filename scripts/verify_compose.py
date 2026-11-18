"""Verify the existing stack. --persistence explicitly recreates its containers.

Run on the VM: python3 scripts/verify_compose.py [--persistence]
Uses only the Python standard library; no host project environment needed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid


REPO = Path(__file__).resolve().parents[1]


def compose(*args, capture=False):
    try:
        return subprocess.run(
            ["docker", "compose", *args], cwd=REPO, check=True,
            capture_output=capture, text=True, stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        if capture and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise


def container_python(service, code, *args):
    result = compose("exec", "-T", service, "python", "-c", code, *args, capture=True)
    return json.loads(result.stdout)


def communicate():
    # Requests originate inside the backend container. No host-published ports
    # or IP addresses are used: this exercises service discovery on the bridge.
    return container_python("backend", """
import json, os, urllib.request
base = os.environ['MLFLOW_TRACKING_URI'].rstrip('/')
with urllib.request.urlopen(base + '/health', timeout=15) as response:
    health = response.status
request = urllib.request.Request(base + '/api/2.0/mlflow/experiments/search',
    data=json.dumps({'max_results': 5}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(request, timeout=15) as response:
    metadata = json.load(response)
with urllib.request.urlopen('http://frontend/healthz', timeout=15) as response:
    frontend = response.status
print(json.dumps({'backend_to_mlflow_health': health,
    'backend_to_mlflow_metadata': 'OK',
    'experiments_returned': len(metadata.get('experiments', [])),
    'backend_to_frontend_health': frontend}))
""")


def experiment_request(operation, payload):
    return container_python("backend", """
import json, os, sys, urllib.error, urllib.request
request = urllib.request.Request(os.environ['MLFLOW_TRACKING_URI'].rstrip('/')
    + '/api/2.0/mlflow/experiments/' + sys.argv[1],
    data=sys.argv[2].encode(), headers={'Content-Type':'application/json'}, method='POST')
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        print(response.read().decode())
except urllib.error.HTTPError as error:
    print(error.read().decode(), file=sys.stderr)
    raise
""", operation, json.dumps(payload))


def marker(service, path, value=None):
    return container_python(service, """
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
if len(sys.argv) == 3:
    path.write_text(sys.argv[2], encoding='utf-8')
print(json.dumps({'value': path.read_text(encoding='utf-8')}))
""", path, *([] if value is None else [value]))["value"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persistence", action="store_true",
                        help="Create verification records and recreate containers; brief downtime.")
    args = parser.parse_args()
    compose("config", "--quiet")
    compose("ps")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "communication": communicate()}
    if args.persistence:
        key = uuid.uuid4().hex
        paths = [("backend", f"/app/data/predictions/.compose-check-{key}"),
                 ("mlflow", f"/mlflow/backend/.compose-check-{key}"),
                 ("mlflow", f"/mlflow/artifacts/.compose-check-{key}")]
        name = f"lk-compose-verification-{key}"
        experiment = experiment_request("create", {"name": name})
        for service, path in paths:
            if marker(service, path, key) != key:
                raise RuntimeError(f"Could not create verification marker: {path}")
        print("Recreating this Compose project's containers to verify persistence...")
        compose("up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "360")
        for service, path in paths:
            if marker(service, path) != key:
                raise RuntimeError(f"Persistence check failed: {service} {path}")
        found = experiment_request("search", {"filter": f"name = '{name}'", "max_results": 10})
        if not any(item["experiment_id"] == experiment["experiment_id"]
                   for item in found.get("experiments", [])):
            raise RuntimeError("MLflow experiment metadata did not survive recreation")
        report["persistence"] = {"status": "passed", "experiment_id": experiment["experiment_id"],
                                 "markers": [path for _, path in paths]}
        report["communication_after_recreation"] = communicate()
        compose("ps")
    output = REPO / "artifacts/compose-verification"
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"VERIFICATION PASSED. Report: {target}")


if __name__ == "__main__":
    main()
