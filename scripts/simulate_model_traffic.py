"""Replay real LK-10 examples at two traffic levels against the local gateway."""

import argparse
from collections import Counter
import json
from pathlib import Path
from time import monotonic, sleep

from verify_model_serving import invoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--phase-seconds", type=int, default=45)
    parser.add_argument("--release-dir", type=Path, default=Path("artifacts/model-serving"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 5 <= args.phase_seconds <= 180:
        parser.error("Use a valid local port and phase duration of 5 to 180 seconds")

    frame = json.loads((args.release_dir / "request.json").read_bytes())["dataframe_split"]
    labels = json.loads((args.release_dir / "expected.json").read_bytes())["predictions"]
    samples = {
        label: json.dumps({"dataframe_split": {"columns": frame["columns"], "data": [row]}}).encode()
        for row, label in zip(frame["data"], labels, strict=True)
    }
    if not {0, 1}.issubset(samples):
        parser.error("The demo requires saved examples for both prediction classes")
    url = f"http://127.0.0.1:{args.port}"
    for rate, mix in ((3, (1, 0)), (12, (1, 1, 1, 0))):
        print(f"Phase target: {rate} req/s for {args.phase_seconds}s", flush=True)
        started = monotonic()
        count = 0
        replicas = Counter()
        while monotonic() - started < args.phase_seconds:
            tick = monotonic()
            label = mix[count % len(mix)]
            response = invoke(url, samples[label], {"predictions": [label]})
            replicas[response["upstream"]] += 1
            count += 1
            sleep(max(0, tick + 1 / rate - monotonic()))
        print(json.dumps({"successful_requests": count, "per_replica": replicas}), flush=True)


if __name__ == "__main__":
    main()
