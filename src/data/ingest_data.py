from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


API_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "pressure_msl",
]


def fetch_weather(
    latitude: float,
    longitude: float,
    timezone_name: str,
) -> tuple[dict, int]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": timezone_name,
        "past_hours": 24,
        "forecast_hours": 1,
    }

    response = httpx.get(
        API_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()

    if "hourly" not in payload:
        raise ValueError("Respons Open-Meteo tidak memiliki field 'hourly'.")

    return payload, response.status_code


def save_raw_data(
    payload: dict,
    status_code: int,
    output_directory: Path,
    latitude: float,
    longitude: float,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")

    output_path = output_directory / f"open_meteo_{timestamp}.json"

    raw_record = {
        "metadata": {
            "source": "open-meteo",
            "endpoint": API_URL,
            "schema_version": "weather-hourly-v1",
            "ingested_at": now.isoformat(),
            "http_status": status_code,
            "requested_coordinate": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "resolved_grid": {
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "elevation": payload.get("elevation"),
            },
            "timezone": payload.get("timezone"),
        },
        "data": payload,
    }

    # Mode "x" mencegah file lama tertimpa.
    with output_path.open("x", encoding="utf-8") as file:
        json.dump(raw_record, file, indent=2, ensure_ascii=False)

    return output_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mengambil data cuaca terbaru dari Open-Meteo."
    )

    parser.add_argument("--latitude", type=float, default=-7.9666)
    parser.add_argument("--longitude", type=float, default=112.6326)
    parser.add_argument("--timezone", default="Asia/Jakarta")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/open_meteo"),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    payload, status_code = fetch_weather(
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        timezone_name=arguments.timezone,
    )

    output_path = save_raw_data(
        payload=payload,
        status_code=status_code,
        output_directory=arguments.output_dir,
        latitude=arguments.latitude,
        longitude=arguments.longitude,
    )

    row_count = len(payload["hourly"]["time"])

    print("Data ingestion berhasil.")
    print(f"Status HTTP  : {status_code}")
    print(f"Jumlah baris: {row_count}")
    print(f"File raw     : {output_path}")


if __name__ == "__main__":
    main()