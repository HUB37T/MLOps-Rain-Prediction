from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class WeatherProvider(Protocol):
    def current_weather(self) -> dict[str, object]:
        """Return the latest provider Weather Record in canonical dashboard units."""


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

    return {
        "status": "partial" if has_unavailable else "complete",
        "current_weather_timestamp": _utc_timestamp(timestamp),
        "variables": variables,
        "warnings": warnings,
        "provider": {
            "name": str(provider_name),
            "attribution": "Data cuaca disediakan oleh Open-Meteo.",
        },
    }
