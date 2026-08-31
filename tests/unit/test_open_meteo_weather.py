from datetime import UTC, datetime

import httpx
import pytest

from rain_prediction.ingestion.weather import (
    OpenMeteoWeatherProvider,
    WeatherProviderError,
)

OPEN_METEO_RESPONSE = {
    "latitude": -7.9666,
    "longitude": 112.6326,
    "timezone": "Asia/Jakarta",
    "current_units": {
        "time": "iso8601",
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


def test_open_meteo_provider_maps_current_weather_and_provenance() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=OPEN_METEO_RESPONSE, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenMeteoWeatherProvider(
        client=client,
        base_url="https://api.open-meteo.com/v1/forecast",
        latitude=-7.9666,
        longitude=112.6326,
        timezone_name="Asia/Jakarta",
    )

    record = provider.current_weather()

    assert len(requests) == 1
    assert requests[0].url.params["latitude"] == "-7.9666"
    assert requests[0].url.params["longitude"] == "112.6326"
    assert requests[0].url.params["timezone"] == "Asia/Jakarta"
    assert requests[0].url.params["wind_speed_unit"] == "kmh"
    assert requests[0].url.params["precipitation_unit"] == "mm"
    assert record["timestamp"] == datetime(2026, 8, 30, 7, tzinfo=UTC)
    assert record["values"] == {
        "temperature_2m": 27.3,
        "relative_humidity_2m": 82.0,
        "precipitation_1h": 0.2,
        "cloud_cover": 75.0,
        "wind_speed_10m": 12.0,
        "wind_direction_10m": 90.0,
        "sea_level_pressure": 1008.0,
    }
    assert record["provider"] == "Open-Meteo"
    assert record["provenance"]["provider_timestamp"] == "2026-08-30T14:00"
    assert record["provenance"]["ingestion_timestamp"].tzinfo == UTC
    assert record["provenance"]["values"]["pressure_msl"] == {
        "original_value": 1008,
        "original_unit": "hPa",
        "converted_value": 1008.0,
        "canonical_unit": "hPa",
    }


def test_open_meteo_provider_raises_a_safe_error_for_bad_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, request=request)

    provider = OpenMeteoWeatherProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://api.open-meteo.com/v1/forecast",
    )

    with pytest.raises(WeatherProviderError, match="Open-Meteo request failed"):
        provider.current_weather()


def test_open_meteo_provider_rejects_missing_current_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"current": {}}, request=request)

    provider = OpenMeteoWeatherProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://api.open-meteo.com/v1/forecast",
    )

    with pytest.raises(WeatherProviderError, match="Open-Meteo response is invalid"):
        provider.current_weather()
