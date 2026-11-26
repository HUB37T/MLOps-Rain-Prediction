"""Instrument the existing MLflow scoring app and expose per-replica metrics."""

from collections import Counter
import json
import os
from pathlib import Path
from time import perf_counter

from mlflow.pyfunc import scoring_server
from prometheus_client import CollectorRegistry, Counter as MetricCounter, Histogram, make_asgi_app
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


REGISTRY = CollectorRegistry()
REQUESTS = MetricCounter(
    "rain_model_requests_total", "Completed MLflow invocation requests", ["status_class"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "rain_model_inference_duration_seconds",
    "MLflow request duration including input validation and response serialization",
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10), registry=REGISTRY,
)
PREDICTIONS = MetricCounter(
    "rain_model_predictions_total", "Successful predictions by returned class", ["label"],
    registry=REGISTRY,
)
for status_class in ("2xx", "3xx", "4xx", "5xx"):
    REQUESTS.labels(status_class)
for label in ("0", "1"):
    PREDICTIONS.labels(label)


class ContainerResources:
    """Expose cgroup v2 measurements without access to the host Docker socket."""

    def collect(self):
        cgroup = Path("/sys/fs/cgroup")
        try:
            cpu = dict(line.split() for line in (cgroup / "cpu.stat").read_text().splitlines())
            yield CounterMetricFamily(
                "rain_container_cpu_seconds", "CPU seconds consumed by the container",
                value=int(cpu["usage_usec"]) / 1_000_000,
            )
        except (OSError, ValueError, KeyError):
            pass
        for filename, name, description in (
            ("memory.current", "memory_bytes", "Memory charged to the container, including cache"),
            ("memory.max", "memory_limit_bytes", "Container memory limit"),
        ):
            try:
                value = (cgroup / filename).read_text().strip()
                if value != "max":
                    yield GaugeMetricFamily(f"rain_container_{name}", description, value=int(value))
            except (OSError, ValueError):
                pass


REGISTRY.register(ContainerResources())


class InvocationMetrics:
    """Observe MLflow responses without changing its request or response format."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/invocations" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status = 500
        body = bytearray()
        capture = True

        async def observe(message):
            nonlocal status, capture
            if message["type"] == "http.response.start":
                status = message["status"]
            if message["type"] == "http.response.body" and status == 200 and capture:
                fragment = message.get("body", b"")
                # Do not retain unbounded prediction batches just for telemetry.
                if len(body) + len(fragment) <= 1024 * 1024:
                    body.extend(fragment)
                else:
                    body.clear()
                    capture = False
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            REQUESTS.labels(f"{status // 100}xx").inc()
            if 200 <= status < 300:
                LATENCY.observe(perf_counter() - started)
            if status == 200 and capture:
                record_classes(body)


def record_classes(body):
    try:
        predictions = json.loads(body)["predictions"]
    except (ValueError, KeyError, TypeError):
        return
    if isinstance(predictions, list):
        for label, count in Counter(value for value in predictions if type(value) is int
                                    and value in (0, 1)).items():
            PREDICTIONS.labels(str(label)).inc(count)


model_path = os.environ.get("RAIN_SERVED_MODEL_PATH", "/opt/ml/model")
scoring_app = scoring_server.init(scoring_server.load_model_with_mlflow_config(model_path))
metrics_app = make_asgi_app(registry=REGISTRY)


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"] == "/metrics":
        await metrics_app(scope, receive, send)
        return
    await instrumented_scoring(scope, receive, send)


instrumented_scoring = InvocationMetrics(scoring_app)
