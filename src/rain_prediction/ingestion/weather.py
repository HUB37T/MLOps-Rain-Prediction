from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx


class WeatherProvider(Protocol):
    def current_weather(self) -> dict[str, object]:
        """Return the latest provider Weather Record in canonical dashboard units."""


class WeatherProviderError(RuntimeError):
    """Raised when a provider Weather Record cannot be retrieved or verified."""


class MockWeatherProvider:
    def current_weather(self) -> dict[str, object]:
        timestamp = datetime.now(UTC).replace(second=0, microsecond=0)
        return {
            "timestamp": timestamp,
            "values": {
                "temperature_2m": 27.3,
                "relative_humidity_2m": 82.0,
                "precipitation_1h": 0.2,
                "cloud_cover": 75.0,
                "wind_speed_10m": 12.0,
                "wind_direction_10m": 90.0,
                "sea_level_pressure": 1008.0,
            },
            "provider": "Open-Meteo",
        }


class OpenMeteoWeatherProvider:
    def __init__(
        self,
        client: httpx.Client | None = None,
        base_url: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        timezone_name: str = "Asia/Jakarta",
    ) -> None:
        self._client = client or httpx.Client(timeout=30.0)
        self._base_url = self._forecast_url(base_url or os.getenv("OPEN_METEO_BASE_URL"))
        self._latitude = latitude if latitude is not None else float(os.getenv("WEATHER_LATITUDE", "-7.9666"))
        self._longitude = longitude if longitude is not None else float(os.getenv("WEATHER_LONGITUDE", "112.6326"))
        self._timezone_name = timezone_name
        self._timezone = ZoneInfo(timezone_name)

    @staticmethod
    def _forecast_url(base_url: str | None) -> str:
        root = (base_url or "https://api.open-meteo.com/v1").rstrip("/")
        return root if root.endswith("/forecast") else f"{root}/forecast"

    def current_weather(self) -> dict[str, object]:
        params = {
            "latitude": self._latitude,
            "longitude": self._longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,"
                "wind_speed_10m,wind_direction_10m,pressure_msl"
            ),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timezone": self._timezone_name,
        }
        try:
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Open-Meteo request failed") from exc

        try:
            payload = response.json()
            current = payload["current"]
            units = payload["current_units"]
            provider_timestamp = current["time"]
            timestamp = datetime.fromisoformat(provider_timestamp)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=self._timezone)
            timestamp = timestamp.astimezone(UTC)

            source_fields = {
                "temperature_2m": ("temperature_2m", "degC"),
                "relative_humidity_2m": ("relative_humidity_2m", "percent"),
                "precipitation_1h": ("precipitation", "mm"),
                "cloud_cover": ("cloud_cover", "percent"),
                "wind_speed_10m": ("wind_speed_10m", "kmh"),
                "wind_direction_10m": ("wind_direction_10m", "degree"),
                "sea_level_pressure": ("pressure_msl", "hPa"),
            }
            values: dict[str, float] = {}
            provenance_values: dict[str, dict[str, object]] = {}
            for field, (source_field, canonical_unit) in source_fields.items():
                original_value = current[source_field]
                converted_value = float(original_value)
                if field == "wind_direction_10m" and converted_value == 360.0:
                    converted_value = 0.0
                values[field] = converted_value
                provenance_values[source_field] = {
                    "original_value": original_value,
                    "original_unit": units[source_field],
                    "converted_value": converted_value,
                    "canonical_unit": canonical_unit,
                }

            return {
                "timestamp": timestamp,
                "values": values,
                "provider": "Open-Meteo",
                "provenance": {
                    "provider_identity": "Open-Meteo",
                    "requested_coordinate": {
                        "latitude": self._latitude,
                        "longitude": self._longitude,
                    },
                    "resolved_grid": {
                        "latitude": payload["latitude"],
                        "longitude": payload["longitude"],
                    },
                    "provider_timestamp": provider_timestamp,
                    "ingestion_timestamp": datetime.now(UTC),
                    "conversion_rule_version": "open-meteo-v1",
                    "values": provenance_values,
                },
            }
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise WeatherProviderError("Open-Meteo response is invalid") from exc


WEATHER_FIELDS = {
    "temperature_2m": ("degC", -100.0, 70.0),
    "relative_humidity_2m": ("percent", 0.0, 100.0),
    "precipitation_1h": ("mm", 0.0, 1000.0),
    "cloud_cover": ("percent", 0.0, 100.0),
    "wind_speed_10m": ("kmh", 0.0, 500.0),
    "wind_direction_10m": ("degree", 0.0, 360.0),
    "sea_level_pressure": ("hPa", 800.0, 1100.0),
}
CORE_FIELDS = {"temperature_2m", "relative_humidity_2m", "precipitation_1h"}


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _freshness_status(seconds: int) -> str:
    if seconds <= 2 * 60 * 60:
        return "fresh"
    if seconds <= 6 * 60 * 60:
        return "stale"
    return "unavailable"


def resolve_current_weather(
    provider: WeatherProvider,
    server_time: datetime,
) -> dict[str, object]:
    record = provider.current_weather()
    timestamp = record.get("timestamp")
    values = record.get("values")
    provider_name = record.get("provider", "Open-Meteo")

    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return {
            "status": "unavailable",
            "variables": {},
            "warnings": [
                {
                    "code": "current_weather_unavailable",
                    "message": "Kondisi cuaca saat ini belum tersedia.",
                }
            ],
        }

    timestamp = timestamp.astimezone(UTC)
    freshness_seconds = int((server_time - timestamp).total_seconds())
    if freshness_seconds < 0:
        return {
            "status": "unavailable",
            "variables": {},
            "warnings": [
                {
                    "code": "current_weather_unavailable",
                    "message": "Kondisi cuaca saat ini belum tersedia.",
                }
            ],
        }

    if not isinstance(values, dict):
        values = {}

    variables: dict[str, dict[str, object]] = {}
    for field, (unit, minimum, maximum) in WEATHER_FIELDS.items():
        raw_value = values.get(field)
        valid_value = isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
        valid_value = valid_value and minimum <= raw_value <= maximum
        value: float | None = float(raw_value) if valid_value else None
        if field == "wind_direction_10m" and value == 360.0:
            value = 0.0
        status = _freshness_status(freshness_seconds) if value is not None else "unavailable"
        variables[field] = {
            "value": value,
            "unit": unit,
            "timestamp": _utc_timestamp(timestamp),
            "freshness_status": status,
            "status": "available" if status != "unavailable" else "unavailable",
        }
        if field == "precipitation_1h":
            variables[field]["interval_start"] = _utc_timestamp(timestamp - timedelta(hours=1))

    available_core = CORE_FIELDS.intersection(
        field for field, variable in variables.items() if variable["status"] == "available"
    )
    section_freshness = _freshness_status(freshness_seconds)
    if not available_core or section_freshness == "unavailable":
        return {
            "status": "unavailable",
            "variables": {},
            "warnings": [
                {
                    "code": "current_weather_unavailable",
                    "message": "Kondisi cuaca saat ini belum tersedia.",
                }
            ],
        }

    has_unavailable = any(variable["status"] == "unavailable" for variable in variables.values())
    warnings: list[dict[str, str]] = []
    if has_unavailable:
        warnings.append(
            {
                "code": "partial_current_weather",
                "message": "Sebagian data cuaca saat ini tidak tersedia.",
            }
        )

    resolved = {
        "status": "partial" if has_unavailable else "complete",
        "current_weather_timestamp": _utc_timestamp(timestamp),
        "variables": variables,
        "warnings": warnings,
        "provider": {
            "name": str(provider_name),
            "attribution": "Data cuaca disediakan oleh Open-Meteo.",
        },
    }
    if "provenance" in record:
        resolved["provenance"] = record["provenance"]
    return resolved
