from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd


API_URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = "2023-10-01"
END_DATE = "2026-09-30"

OUTPUT_DIRECTORY = Path("data/raw/open_meteo_history")
OUTPUT_FILE = OUTPUT_DIRECTORY / (
    f"open_meteo_history_{START_DATE.replace('-', '')}_"
    f"{END_DATE.replace('-', '')}.json"
)

PARAMS = {
    "latitude": -7.9666,
    "longitude": 112.6326,
    "start_date": START_DATE,
    "end_date": END_DATE,
    "hourly": [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "rain",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
        "pressure_msl",
    ],
    "timezone": "Asia/Jakarta",
    "models": "era5",
}


def validate_response(payload: dict) -> pd.DataFrame:
    """Memeriksa struktur dasar data historis Open-Meteo."""

    if "hourly" not in payload:
        raise ValueError("Respons API tidak memiliki bagian 'hourly'.")

    dataframe = pd.DataFrame(payload["hourly"])

    required_columns = {
        "time",
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "rain",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
        "pressure_msl",
    }

    missing_columns = required_columns.difference(dataframe.columns)

    if missing_columns:
        raise ValueError(
            f"Kolom berikut tidak ditemukan: {sorted(missing_columns)}"
        )

    dataframe["time"] = pd.to_datetime(dataframe["time"], errors="raise")

    if dataframe["time"].duplicated().any():
        raise ValueError("Ditemukan timestamp duplikat pada data historis.")

    if not dataframe["time"].is_monotonic_increasing:
        raise ValueError("Timestamp data tidak tersusun secara berurutan.")

    return dataframe


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print(
        f"Mengambil data historis {START_DATE} sampai {END_DATE}..."
    )

    response = httpx.get(
        API_URL,
        params=PARAMS,
        timeout=120,
    )
    response.raise_for_status()

    payload = response.json()
    dataframe = validate_response(payload)

    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Pengambilan data historis berhasil.")
    print(f"Status HTTP       : {response.status_code}")
    print(f"Jumlah baris      : {len(dataframe):,}")
    print(f"Waktu pertama     : {dataframe['time'].min()}")
    print(f"Waktu terakhir    : {dataframe['time'].max()}")
    print(f"Timestamp duplikat: {dataframe['time'].duplicated().sum()}")
    print(f"Jumlah nilai kosong:\n{dataframe.isna().sum()}")
    print(f"File raw          : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
