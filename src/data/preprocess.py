from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


PROJECT_TIMEZONE = "Asia/Jakarta"
RAW_SCHEMA_VERSION = "weather-hourly-v1"
PROCESSED_SCHEMA_VERSION = "weather-clean-v2"

REQUIRED_COLUMNS = [
    "time",
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "pressure_msl",
]

NUMERIC_COLUMNS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "pressure_msl",
]

# Unit yang diharapkan dari ingest_data.py/Open-Meteo. Pipeline berhenti
# memproses sebuah file jika unit berubah agar data tidak diam-diam tercampur.
EXPECTED_UNITS = {
    "time": "iso8601",
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "precipitation": "mm",
    "rain": "mm",
    "cloud_cover": "%",
    "wind_speed_10m": "km/h",
    "wind_direction_10m": "°",
    "pressure_msl": "hPa",
}

# Rentang keras bersifat pemeriksaan integritas, bukan rentang tipikal Malang.
# Nilai di luar rentang ini tidak aman digunakan dan masuk quarantine.
HARD_RANGES = {
    "temperature_2m": (-100.0, 70.0),
    "relative_humidity_2m": (0.0, 100.0),
    "precipitation": (0.0, 1000.0),
    "rain": (0.0, 1000.0),
    "cloud_cover": (0.0, 100.0),
    "wind_speed_10m": (0.0, 500.0),
    "wind_direction_10m": (0.0, 360.0),
    "pressure_msl": (800.0, 1100.0),
}


class RawFileValidationError(ValueError):
    """Raised when one raw file cannot safely enter preprocessing."""


def _require_mapping(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise RawFileValidationError(
            f"Field '{field_name}' harus berupa object JSON."
        )
    return value


def _validate_units(hourly_units: dict, file_path: Path) -> None:
    mismatches: list[str] = []

    for column, expected_unit in EXPECTED_UNITS.items():
        actual_unit = hourly_units.get(column)
        if actual_unit != expected_unit:
            mismatches.append(
                f"{column}: diharapkan {expected_unit!r}, diterima {actual_unit!r}"
            )

    if mismatches:
        details = "; ".join(mismatches)
        raise RawFileValidationError(
            f"{file_path.name} memiliki unit tidak sesuai: {details}"
        )


def _validate_hourly_arrays(hourly_data: dict, file_path: Path) -> None:
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(hourly_data))
    if missing_columns:
        raise RawFileValidationError(
            f"{file_path.name} kehilangan kolom: {missing_columns}"
        )

    lengths: dict[str, int] = {}
    for column in REQUIRED_COLUMNS:
        values = hourly_data[column]
        if not isinstance(values, list):
            raise RawFileValidationError(
                f"{file_path.name}: kolom '{column}' harus berupa array."
            )
        lengths[column] = len(values)

    if not lengths["time"]:
        raise RawFileValidationError(
            f"{file_path.name} tidak memiliki observasi hourly."
        )

    if len(set(lengths.values())) != 1:
        raise RawFileValidationError(
            f"{file_path.name} memiliki panjang array yang berbeda: {lengths}"
        )


def read_raw_file(file_path: Path) -> pd.DataFrame:
    """Read and validate one immutable raw Open-Meteo response."""
    try:
        with file_path.open("r", encoding="utf-8") as file:
            raw_record = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RawFileValidationError(
            f"Tidak dapat membaca {file_path.name}: {exc}"
        ) from exc

    raw_record = _require_mapping(raw_record, "root")
    metadata = _require_mapping(raw_record.get("metadata"), "metadata")
    api_data = _require_mapping(raw_record.get("data"), "data")
    hourly_data = _require_mapping(api_data.get("hourly"), "data.hourly")
    hourly_units = _require_mapping(
        api_data.get("hourly_units"),
        "data.hourly_units",
    )

    if metadata.get("http_status") != 200:
        raise RawFileValidationError(
            f"{file_path.name} memiliki HTTP status {metadata.get('http_status')!r}."
        )

    if metadata.get("schema_version") != RAW_SCHEMA_VERSION:
        raise RawFileValidationError(
            f"{file_path.name} memiliki schema_version "
            f"{metadata.get('schema_version')!r}, bukan {RAW_SCHEMA_VERSION!r}."
        )

    provider_timezone = metadata.get("timezone") or api_data.get("timezone")
    if provider_timezone != PROJECT_TIMEZONE:
        raise RawFileValidationError(
            f"{file_path.name} menggunakan timezone {provider_timezone!r}, "
            f"bukan {PROJECT_TIMEZONE!r}."
        )

    requested = _require_mapping(
        metadata.get("requested_coordinate"),
        "metadata.requested_coordinate",
    )
    resolved = _require_mapping(
        metadata.get("resolved_grid"),
        "metadata.resolved_grid",
    )

    _validate_hourly_arrays(hourly_data, file_path)
    _validate_units(hourly_units, file_path)

    frame = pd.DataFrame({column: hourly_data[column] for column in REQUIRED_COLUMNS})
    frame["location_id"] = "malang-filkom"
    frame["requested_latitude"] = requested.get("latitude")
    frame["requested_longitude"] = requested.get("longitude")
    frame["resolved_latitude"] = resolved.get("latitude")
    frame["resolved_longitude"] = resolved.get("longitude")
    frame["elevation_m"] = resolved.get("elevation")
    frame["provider_timezone"] = provider_timezone
    frame["ingested_at"] = metadata.get("ingested_at")
    frame["source"] = metadata.get("source")
    frame["source_endpoint"] = metadata.get("endpoint")
    frame["source_file"] = file_path.name
    frame["raw_schema_version"] = metadata.get("schema_version")

    return frame


def load_raw_data(raw_directory: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load every raw file independently so one corrupt file does not stop all data."""
    raw_files = sorted(raw_directory.glob("*.json"))

    if not raw_files:
        raise FileNotFoundError(f"Tidak ada file JSON di {raw_directory}.")

    frames: list[pd.DataFrame] = []
    file_errors: list[dict[str, str]] = []

    for file_path in raw_files:
        try:
            frames.append(read_raw_file(file_path))
        except (RawFileValidationError, KeyError, TypeError, ValueError) as exc:
            file_errors.append(
                {
                    "source_file": file_path.name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "detected_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame()
    )
    return combined, pd.DataFrame(file_errors)


def _append_reason(
    reasons: pd.Series,
    mask: pd.Series,
    reason: str,
) -> None:
    safe_mask = mask.fillna(False).astype(bool)
    for index in reasons.index[safe_mask]:
        existing = reasons.at[index]
        reasons.at[index] = f"{existing};{reason}" if existing else reason


def _parse_provider_time(
    values: pd.Series,
    timezone_name: str,
) -> tuple[pd.Series, pd.Series]:
    parsed = pd.to_datetime(values, errors="coerce")

    try:
        provider_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RawFileValidationError(
            f"Timezone tidak dikenali: {timezone_name!r}."
        ) from exc

    if parsed.dt.tz is None:
        local_time = parsed.dt.tz_localize(
            provider_timezone,
            ambiguous="NaT",
            nonexistent="NaT",
        )
    else:
        local_time = parsed.dt.tz_convert(provider_timezone)

    utc_time = local_time.dt.tz_convert("UTC")
    return local_time, utc_time


def clean_data(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean rows without imputing values or creating training features."""
    if frame.empty:
        return frame.copy(), frame.copy()

    cleaned = frame.copy()
    provider_time_wib, event_time_utc = _parse_provider_time(
        cleaned["time"],
        PROJECT_TIMEZONE,
    )
    cleaned["event_time_wib"] = provider_time_wib
    cleaned["event_time_utc"] = event_time_utc
    cleaned["ingested_at_utc"] = pd.to_datetime(
        cleaned["ingested_at"],
        errors="coerce",
        utc=True,
    )

    for column in NUMERIC_COLUMNS:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    # 360° sama dengan 0° dan dinormalisasi untuk representasi kanonis.
    cleaned.loc[cleaned["wind_direction_10m"] == 360.0, "wind_direction_10m"] = 0.0

    quality_reasons = pd.Series("", index=cleaned.index, dtype="object")
    quality_warnings = pd.Series("", index=cleaned.index, dtype="object")

    _append_reason(
        quality_reasons,
        cleaned["event_time_utc"].isna(),
        "invalid_event_time",
    )
    _append_reason(
        quality_reasons,
        cleaned["ingested_at_utc"].isna(),
        "invalid_ingested_at",
    )

    for column in NUMERIC_COLUMNS:
        _append_reason(
            quality_reasons,
            cleaned[column].isna(),
            f"missing_or_non_numeric_{column}",
        )

        minimum, maximum = HARD_RANGES[column]
        _append_reason(
            quality_reasons,
            cleaned[column].notna() & ~cleaned[column].between(minimum, maximum),
            f"out_of_range_{column}",
        )

    # Rentang tipikal lokal hanya menjadi warning agar anomali nyata tidak dibuang.
    _append_reason(
        quality_warnings,
        cleaned["temperature_2m"].notna()
        & ~cleaned["temperature_2m"].between(-10.0, 45.0),
        "unusual_temperature_for_malang",
    )
    _append_reason(
        quality_warnings,
        cleaned["pressure_msl"].notna()
        & ~cleaned["pressure_msl"].between(850.0, 1085.0),
        "unusual_sea_level_pressure",
    )
    _append_reason(
        quality_warnings,
        cleaned["rain"].notna()
        & cleaned["precipitation"].notna()
        & (cleaned["rain"] > cleaned["precipitation"] + 0.001),
        "rain_exceeds_total_precipitation",
    )

    ingestion_hour_wib = cleaned["ingested_at_utc"].dt.tz_convert(
        PROJECT_TIMEZONE
    ).dt.floor("h")
    cleaned["is_complete_hour"] = (
        cleaned["event_time_wib"].notna()
        & ingestion_hour_wib.notna()
        & (cleaned["event_time_wib"] <= ingestion_hour_wib)
    )
    cleaned["record_type"] = cleaned["is_complete_hour"].map(
        {True: "completed_hour", False: "forecast_or_incomplete"}
    )

    hard_invalid = quality_reasons.ne("")
    excluded_future = ~hard_invalid & ~cleaned["is_complete_hour"]
    _append_reason(
        quality_reasons,
        excluded_future,
        "forecast_or_incomplete_hour_excluded",
    )

    cleaned["quality_reason"] = quality_reasons
    cleaned["quality_warning"] = quality_warnings
    cleaned["processed_schema_version"] = PROCESSED_SCHEMA_VERSION

    invalid_rows = cleaned.loc[hard_invalid].copy()
    invalid_rows["quality_status"] = "invalid"

    future_rows = cleaned.loc[excluded_future].copy()
    future_rows["quality_status"] = "excluded"

    candidates = cleaned.loc[~hard_invalid & ~excluded_future].copy()
    candidates = candidates.sort_values(
        by=["location_id", "event_time_utc", "ingested_at_utc", "source_file"],
        kind="stable",
    )

    # Simpan versi terbaru, tetapi pertahankan versi lama di quarantine untuk audit.
    superseded_mask = candidates.duplicated(
        subset=["location_id", "event_time_utc"],
        keep="last",
    )
    superseded_rows = candidates.loc[superseded_mask].copy()
    superseded_rows["quality_status"] = "excluded"
    superseded_rows["quality_reason"] = "superseded_by_newer_ingestion"

    valid_data = candidates.loc[~superseded_mask].copy()
    valid_data["quality_status"] = "valid"
    valid_data["quality_reason"] = ""
    valid_data = valid_data.sort_values(
        by=["location_id", "event_time_utc"],
        kind="stable",
    ).reset_index(drop=True)

    previous_gap = valid_data.groupby("location_id")["event_time_utc"].diff()
    valid_data["has_previous_hour_gap"] = (
        previous_gap.notna() & previous_gap.ne(pd.Timedelta(hours=1))
    )

    quarantine_data = pd.concat(
        [invalid_rows, future_rows, superseded_rows],
        ignore_index=True,
    )
    if not quarantine_data.empty:
        quarantine_data = quarantine_data.sort_values(
            by=["source_file", "event_time_utc"],
            kind="stable",
            na_position="last",
        ).reset_index(drop=True)

    # Kolom asli dipertahankan sebagai provider_time untuk audit, sedangkan
    # event_time_utc menjadi waktu kanonis untuk pipeline berikutnya.
    valid_data = valid_data.rename(columns={"time": "provider_time"})
    quarantine_data = quarantine_data.rename(columns={"time": "provider_time"})

    return valid_data, quarantine_data


def _write_csv_atomically(frame: pd.DataFrame, output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError(f"File output sudah ada: {output_path}")

    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        frame.to_csv(temporary_path, index=False)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def save_results(
    valid_data: pd.DataFrame,
    quarantine_data: pd.DataFrame,
    file_errors: pd.DataFrame,
    processed_directory: Path,
    quarantine_directory: Path,
) -> tuple[Path | None, Path | None, Path | None]:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    processed_at = now.isoformat()

    processed_directory.mkdir(parents=True, exist_ok=True)
    quarantine_directory.mkdir(parents=True, exist_ok=True)

    processed_path: Path | None = None
    quarantine_path: Path | None = None
    file_errors_path: Path | None = None

    if not valid_data.empty:
        valid_output = valid_data.copy()
        valid_output["processed_at_utc"] = processed_at
        processed_path = processed_directory / f"weather_hourly_{timestamp}.csv"
        _write_csv_atomically(valid_output, processed_path)

    if not quarantine_data.empty:
        quarantine_output = quarantine_data.copy()
        quarantine_output["processed_at_utc"] = processed_at
        quarantine_path = (
            quarantine_directory / f"weather_quarantine_{timestamp}.csv"
        )
        _write_csv_atomically(quarantine_output, quarantine_path)

    if not file_errors.empty:
        file_errors_path = (
            quarantine_directory / f"preprocess_file_errors_{timestamp}.csv"
        )
        _write_csv_atomically(file_errors, file_errors_path)

    return processed_path, quarantine_path, file_errors_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Memvalidasi dan membersihkan data mentah Open-Meteo tanpa "
            "menggunakan data forecast sebagai observasi training."
        )
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw/open_meteo"),
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed"),
    )
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=Path("data/quarantine"),
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    raw_data, file_errors = load_raw_data(arguments.raw_dir)

    if raw_data.empty:
        _, _, file_errors_path = save_results(
            valid_data=pd.DataFrame(),
            quarantine_data=pd.DataFrame(),
            file_errors=file_errors,
            processed_directory=arguments.processed_dir,
            quarantine_directory=arguments.quarantine_dir,
        )
        if file_errors_path:
            print(f"Manifest error file: {file_errors_path}")
        raise SystemExit("Tidak ada raw file valid yang dapat diproses.")

    valid_data, quarantine_data = clean_data(raw_data)
    processed_path, quarantine_path, file_errors_path = save_results(
        valid_data=valid_data,
        quarantine_data=quarantine_data,
        file_errors=file_errors,
        processed_directory=arguments.processed_dir,
        quarantine_directory=arguments.quarantine_dir,
    )

    print("Preprocessing selesai.")
    print(f"Total data valid       : {len(valid_data)}")
    print(f"Total data quarantine  : {len(quarantine_data)}")
    print(f"Total raw file bermasalah: {len(file_errors)}")
    print(f"Processed file         : {processed_path or '-'}")
    print(f"Quarantine file        : {quarantine_path or '-'}")
    print(f"File error manifest    : {file_errors_path or '-'}")

    if valid_data.empty:
        raise SystemExit("Tidak ada baris valid yang aman digunakan.")


if __name__ == "__main__":
    main()
