"""Verify actual MLflow HTTP predictions and (optionally) all Compose replicas.

Standard library only. Never starts, stops or scales containers.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def compose(*args):
    return subprocess.check_output(
        ["docker", "compose", "--profile", "serving", *args], cwd=ROOT,
        text=True, stdin=subprocess.DEVNULL).strip()


def invoke(url, payload, expected):
    request = urllib.request.Request(url.rstrip("/") + "/invocations", data=payload,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
            attempts = response.headers.get("X-Model-Upstream")
            # Nginx lists all attempted peers when retrying after a scale-down.
            # Count the last (successful) peer rather than the removed replica.
            upstream = attempts.split(",")[-1].strip() if attempts else None
            if response.status != 200 or body != expected:
                raise ValueError(f"Prediction differs from the frozen Production model: {body}")
            return {"http_status": response.status, "response": body, "upstream": upstream,
                    "upstream_attempts": attempts}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read().decode()}") from error


def verify_replicas(expected_count, image, artifact_sha256):
    ids = compose("ps", "--all", "-q", "model-api").splitlines()
    if len(ids) != expected_count:
        raise ValueError(f"Expected {expected_count} replicas, found {len(ids)}")
    containers = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True))
    expected_image = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    details = []
    for item in containers:
        if item["Image"] != expected_image:
            raise ValueError("Replica is using a different image from the prepared release")
        if not item["State"]["Running"] or item["State"].get("Health", {}).get("Status") != "healthy":
            raise ValueError(f"Replica not healthy: {item['Name']}")
        fingerprint = subprocess.check_output(
            ["docker", "exec", item["Id"], "python", "-c", """
import hashlib
from pathlib import Path
root = Path('/opt/ml/model')
digest = hashlib.sha256()
for path in sorted(p for p in root.rglob('*') if p.is_file()):
    digest.update(path.relative_to(root).as_posix().encode() + b'\\0')
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
print(digest.hexdigest())
"""], text=True, stdin=subprocess.DEVNULL).strip()
        if fingerprint != artifact_sha256:
            raise ValueError(f"Replica model bytes do not match the exported release: {item['Name']}")
        addresses = [f"{network['IPAddress']}:8080"
                     for network in item["NetworkSettings"]["Networks"].values()
                     if network.get("IPAddress")]
        details.append({"name": item["Name"].lstrip("/"), "health": "healthy",
                        "image_id": item["Image"], "artifact_sha256": fingerprint,
                        "addresses": addresses})
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5001")
    parser.add_argument("--release-dir", type=Path, default=Path("artifacts/model-serving"))
    parser.add_argument("--replicas", type=int, help="Also check count, image, health and request routing")
    parser.add_argument("--image", default="rain-risk-model:v2")
    parser.add_argument("--requests", type=int, default=30)
    args = parser.parse_args()
    if args.requests < 1 or (args.replicas is not None and args.replicas < 1):
        parser.error("Request and replica counts must be positive")
    if args.replicas and args.requests < args.replicas * 5:
        parser.error("Use at least five requests per replica to check distribution")
    payload = (args.release_dir / "request.json").read_bytes()
    expected = json.loads((args.release_dir / "expected.json").read_text())
    release = json.loads((args.release_dir / "release.json").read_text())
    details = verify_replicas(args.replicas, args.image, release["artifact_sha256"]) if args.replicas else []
    first = invoke(args.url, payload, expected)
    with ThreadPoolExecutor(max_workers=min(6, args.requests)) as pool:
        results = list(pool.map(lambda _: invoke(args.url, payload, expected), range(args.requests)))
    distribution = Counter(result["upstream"] for result in results if result["upstream"])
    if args.replicas:
        live = {address for item in details for address in item["addresses"]}
        seen = set(distribution)
        if not seen.issubset(live) or not all(seen.intersection(item["addresses"]) for item in details):
            raise ValueError(f"Requests did not reach every live replica: {dict(distribution)}")
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": args.url, "model_uri": release["model_uri"],
        "artifact_sha256": release["artifact_sha256"],
        "input": json.loads(payload), "first_prediction": first,
        "successful_requests": len(results), "replicas": details,
        "upstream_distribution": dict(distribution), "status": "passed",
    }
    target = args.release_dir / f"verification-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"VERIFICATION PASSED: {target}")


if __name__ == "__main__":
    main()
