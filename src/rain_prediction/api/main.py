from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import FastAPI


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""


class Predictor(Protocol):
    def rain_probability(self) -> float:
        """Return the mock model's unrounded Rain Probability."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class MockPredictor:
    def rain_probability(self) -> float:
        return 0.499


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _current_prediction(clock: Clock, predictor: Predictor) -> dict[str, object]:
    server_time = clock.now().astimezone(UTC)
    official_time = server_time.replace(minute=0, second=0, microsecond=0)
    horizon_start = official_time + timedelta(hours=1)
    horizon_end = official_time + timedelta(hours=4)
    feature_timestamp = official_time
    probability = predictor.rain_probability()

    return {
        "server_time": _utc_timestamp(server_time),
        "primary_location": {
            "id": "filkom-ub",
            "name": "FILKOM Universitas Brawijaya",
            "requested_coordinate": {"latitude": -7.9666, "longitude": 112.6326},
            "resolved_grid": {"latitude": -7.9666, "longitude": 112.6326},
        },
        "status": "available",
        "active_configuration": {
            "decision_threshold": 0.5,
            "risk_configuration_version": "risk-v1",
        },
        "prediction": {
            "prediction_record_id": f"pred-{_utc_timestamp(official_time)}",
            "official_prediction_time": _utc_timestamp(official_time),
            "actual_generation_time": _utc_timestamp(server_time),
            "prediction_horizon": {
                "start": _utc_timestamp(horizon_start),
                "end": _utc_timestamp(horizon_end),
            },
            "rain_probability": probability,
            "predicted_class": "rain" if probability >= 0.5 else "no_rain",
            "decision_threshold": 0.5,
            "near_threshold": abs(probability - 0.5) <= 0.05,
            "risk_level": "moderate",
            "risk_boundaries": {
                "low_to_moderate": 0.3,
                "moderate_to_high": 0.7,
            },
            "risk_configuration_version": "risk-v1",
            "preparation_action": "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
            "preparation_copy_version": "prep-v1",
            "feature_timestamp": _utc_timestamp(feature_timestamp),
            "data_freshness_seconds": int((server_time - feature_timestamp).total_seconds()),
            "freshness_status": "fresh",
            "model": {
                "name": "baseline",
                "version": "baseline-v1",
                "status": "experimental",
                "latest_validation_date": "2026-08-29",
            },
        },
        "warnings": [],
    }


def create_app(clock: Clock | None = None, predictor: Predictor | None = None) -> FastAPI:
    app = FastAPI(title="Rain Risk API", version="0.1.0")
    current_clock = clock or SystemClock()
    current_predictor = predictor or MockPredictor()

    @app.get("/api/v1/predictions/current")
    def get_current_prediction() -> dict[str, object]:
        return _current_prediction(current_clock, current_predictor)

    return app


app = create_app()
