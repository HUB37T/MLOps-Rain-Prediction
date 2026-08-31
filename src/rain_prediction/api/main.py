from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from fastapi import FastAPI

from rain_prediction.inference.lifecycle import (
    MockPredictionRepository,
    PredictionRepository,
    resolve_current_prediction,
)
from rain_prediction.ingestion.weather import (
    OpenMeteoWeatherProvider,
    WeatherProvider,
    WeatherProviderError,
    resolve_current_weather,
)


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


def create_app(
    clock: Clock | None = None,
    predictor: Predictor | None = None,
    weather_provider: WeatherProvider | None = None,
    prediction_repository: PredictionRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="Rain Risk API", version="0.1.0")
    current_clock = clock or SystemClock()
    current_predictor = predictor or MockPredictor()
    current_weather_provider = weather_provider or OpenMeteoWeatherProvider()
    current_prediction_repository = prediction_repository or MockPredictionRepository(
        current_clock, current_predictor
    )

    @app.get("/api/v1/predictions/current")
    def get_current_prediction() -> dict[str, object]:
        return resolve_current_prediction(current_prediction_repository, current_clock.now())

    @app.get("/api/v1/weather/current")
    def get_current_weather() -> dict[str, object]:
        server_time = current_clock.now().astimezone(UTC)
        try:
            weather = resolve_current_weather(current_weather_provider, server_time)
        except WeatherProviderError:
            return {
                "server_time": _utc_timestamp(server_time),
                "primary_location": {
                    "id": "filkom-ub",
                    "name": "FILKOM Universitas Brawijaya",
                },
                "status": "unavailable",
                "variables": {},
                "warnings": [
                    {
                        "code": "weather_provider_unavailable",
                        "message": "Kondisi cuaca saat ini belum tersedia.",
                    }
                ],
            }
        return {
            "server_time": _utc_timestamp(server_time),
            "primary_location": {
                "id": "filkom-ub",
                "name": "FILKOM Universitas Brawijaya",
            },
            **weather,
        }

    return app


app = create_app()
