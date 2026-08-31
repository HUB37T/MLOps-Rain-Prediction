from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from rain_prediction.api.main import create_app
from rain_prediction.ingestion.weather import OpenMeteoWeatherProvider


class FixedClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def now(self) -> datetime:
        return self.current_time


class StaticWeatherProvider:
    def __init__(self, values: dict[str, float | None], timestamp: datetime) -> None:
        self.values = values
        self.timestamp = timestamp

    def current_weather(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "values": self.values,
            "provider": "Open-Meteo",
        }


CURRENT_TIME = datetime(2026, 8, 30, 7, 5, tzinfo=UTC)
WEATHER_TIME = CURRENT_TIME - timedelta(minutes=5)
COMPLETE_VALUES = {
    "temperature_2m": 27.3,
    "relative_humidity_2m": 82.0,
    "precipitation_1h": 0.2,
    "cloud_cover": 75.0,
    "wind_speed_10m": 12.0,
    "wind_direction_10m": 90.0,
    "sea_level_pressure": 1008.0,
}


def test_current_weather_returns_the_complete_dashboard_contract() -> None:
    client = TestClient(
        create_app(
            clock=FixedClock(CURRENT_TIME),
            weather_provider=StaticWeatherProvider(COMPLETE_VALUES, WEATHER_TIME),
        )
    )

    response = client.get("/api/v1/weather/current")

    assert response.status_code == 200
    body = response.json()
    assert body["server_time"] == "2026-08-30T07:05:00Z"
    assert body["primary_location"] == {
        "id": "filkom-ub",
        "name": "FILKOM Universitas Brawijaya",
    }
    assert body["status"] == "complete"
    assert body["current_weather_timestamp"] == "2026-08-30T07:00:00Z"
    assert body["variables"] == {
        "temperature_2m": {
            "value": 27.3,
            "unit": "degC",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "relative_humidity_2m": {
            "value": 82.0,
            "unit": "percent",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "precipitation_1h": {
            "value": 0.2,
            "unit": "mm",
            "interval_start": "2026-08-30T06:00:00Z",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "cloud_cover": {
            "value": 75.0,
            "unit": "percent",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "wind_speed_10m": {
            "value": 12.0,
            "unit": "kmh",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "wind_direction_10m": {
            "value": 90.0,
            "unit": "degree",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
        "sea_level_pressure": {
            "value": 1008.0,
            "unit": "hPa",
            "timestamp": "2026-08-30T07:00:00Z",
            "freshness_status": "fresh",
            "status": "available",
        },
    }
    assert body["provider"] == {
        "name": "Open-Meteo",
        "attribution": "Data cuaca disediakan oleh Open-Meteo.",
    }


def test_current_weather_marks_a_missing_variable_as_partial() -> None:
    values = {**COMPLETE_VALUES, "wind_speed_10m": None}
    client = TestClient(
        create_app(
            clock=FixedClock(CURRENT_TIME),
            weather_provider=StaticWeatherProvider(values, WEATHER_TIME),
        )
    )

    body = client.get("/api/v1/weather/current").json()

    assert body["status"] == "partial"
    assert body["variables"]["wind_speed_10m"] == {
        "value": None,
        "unit": "kmh",
        "timestamp": "2026-08-30T07:00:00Z",
        "freshness_status": "unavailable",
        "status": "unavailable",
    }
    assert body["warnings"] == [
        {"code": "partial_current_weather", "message": "Sebagian data cuaca saat ini tidak tersedia."}
    ]


def test_current_weather_is_unavailable_when_all_core_values_are_missing() -> None:
    values = {
        **COMPLETE_VALUES,
        "temperature_2m": None,
        "relative_humidity_2m": None,
        "precipitation_1h": None,
    }
    client = TestClient(
        create_app(
            clock=FixedClock(CURRENT_TIME),
            weather_provider=StaticWeatherProvider(values, WEATHER_TIME),
        )
    )

    body = client.get("/api/v1/weather/current").json()

    assert body["status"] == "unavailable"
    assert body["variables"] == {}
    assert body["warnings"] == [
        {"code": "current_weather_unavailable", "message": "Kondisi cuaca saat ini belum tersedia."}
    ]


def test_open_meteo_provider_feeds_the_current_weather_http_contract() -> None:
    provider_response = {
        "latitude": -7.9666,
        "longitude": 112.6326,
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "precipitation": "mm",
            "cloud_cover": "%",
            "wind_speed_10m": "km/h",
            "wind_direction_10m": "°",
            "pressure_msl": "hPa",
        },
        "current": {
            "time": "2026-08-30T14:00",
            "temperature_2m": 27.3,
            "relative_humidity_2m": 82,
            "precipitation": 0.2,
            "cloud_cover": 75,
            "wind_speed_10m": 12,
            "wind_direction_10m": 90,
            "pressure_msl": 1008,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_response, request=request)

    provider = OpenMeteoWeatherProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://api.open-meteo.com/v1/forecast",
        timezone_name="Asia/Jakarta",
    )
    client = TestClient(create_app(clock=FixedClock(CURRENT_TIME), weather_provider=provider))

    body = client.get("/api/v1/weather/current").json()

    assert body["status"] == "complete"
    assert body["variables"]["sea_level_pressure"]["value"] == 1008.0
    assert body["provenance"]["provider_identity"] == "Open-Meteo"
