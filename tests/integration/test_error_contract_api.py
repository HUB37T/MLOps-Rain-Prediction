from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rain_prediction.api.main import create_app
from rain_prediction.inference.lifecycle import PredictionServiceError
from rain_prediction.ingestion.weather import WeatherProviderError


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 7, 5, tzinfo=UTC)


class FailingWeatherProvider:
    def current_weather(self) -> dict[str, object]:
        raise WeatherProviderError("provider diagnostics must not escape")


class FailingPredictionRepository:
    def list_records(self) -> list[dict[str, object]]:
        raise PredictionServiceError("repository diagnostics must not escape")


def test_weather_provider_failure_returns_a_safe_502_error() -> None:
    client = TestClient(create_app(clock=FixedClock(), weather_provider=FailingWeatherProvider()))

    response = client.get("/api/v1/weather/current")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "weather_provider_unavailable",
            "message": "Weather data is temporarily unavailable.",
        }
    }
    assert "diagnostics" not in response.text


def test_prediction_service_failure_returns_a_safe_503_error() -> None:
    client = TestClient(create_app(clock=FixedClock(), prediction_repository=FailingPredictionRepository()))

    response = client.get("/api/v1/predictions/current")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "prediction_service_unavailable",
            "message": "Prediction service is temporarily unavailable.",
        }
    }
    assert "diagnostics" not in response.text


def test_history_service_failure_returns_a_safe_503_error() -> None:
    client = TestClient(create_app(clock=FixedClock(), prediction_repository=FailingPredictionRepository()))

    response = client.get("/api/v1/predictions/history?slots=24")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "prediction_service_unavailable"
