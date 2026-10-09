from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping, Protocol

import pandas as pd

from rain_prediction.inference.model import (
    RainModelPredictor,
    RainPrediction,
)
from rain_prediction.inference.repository import (
    SQLitePredictionRepository,
)


class PredictionJobError(RuntimeError):
    """Raised when an hourly prediction cannot be generated."""


class PredictionGenerator(Protocol):
    @property
    def feature_columns(self) -> tuple[str, ...]:
        """Return features required by the model."""

    def predict(
        self,
        feature_values: Mapping[str, object],
    ) -> RainPrediction:
        """Generate one validated rain prediction."""


class PredictionWriter(Protocol):
    def save_record(
        self,
        record: dict[str, object],
    ) -> bool:
        """Persist a Prediction Record idempotently."""


@dataclass(frozen=True)
class PredictionJobResult:
    record: dict[str, object]
    inserted: bool
    processed_file: Path


def run_prediction_job(
    predictor: PredictionGenerator,
    repository: PredictionWriter,
    processed_directory: Path,
    generated_at: datetime,
) -> PredictionJobResult:
    if generated_at.tzinfo is None:
        raise PredictionJobError(
            "generated_at harus memiliki timezone."
        )

    generated_at = generated_at.astimezone(UTC)
    official_time = generated_at.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    generation_deadline = official_time + timedelta(
        minutes=10
    )

    if generated_at >= generation_deadline:
        raise PredictionJobError(
            "Prediction job harus selesai sebelum menit ke-10."
        )

    (
        feature_values,
        feature_timestamp,
        processed_file,
    ) = _load_latest_feature_row(
        processed_directory=processed_directory,
        feature_columns=list(
            predictor.feature_columns
        ),
        official_time=official_time,
    )

    prediction = predictor.predict(feature_values)
    risk_level = _risk_level(prediction.probability)

    record: dict[str, object] = {
        "prediction_record_id": (
            "pred-"
            + official_time.strftime(
                "%Y%m%dT%H%M%SZ"
            )
        ),
        "official_prediction_time": official_time,
        "actual_generation_time": generated_at,
        "prediction_horizon": {
            "start": (
                official_time + timedelta(hours=1)
            ),
            "end": (
                official_time + timedelta(hours=4)
            ),
        },
        "rain_probability": prediction.probability,
        "predicted_class": (
            prediction.predicted_class
        ),
        "decision_threshold": (
            prediction.decision_threshold
        ),
        "near_threshold": prediction.near_threshold,
        "risk_level": risk_level,
        "risk_boundaries": {
            "low_to_moderate": 0.3,
            "moderate_to_high": 0.7,
        },
        "risk_configuration_version": "risk-v1",
        "preparation_action": (
            _preparation_action(risk_level)
        ),
        "preparation_copy_version": "prep-v1",
        "feature_timestamp": feature_timestamp,
        "feature_source_file": processed_file.name,
        "model": {
            "name": prediction.model_name,
            "version": prediction.model_version,
            "status": "experimental",
            "latest_validation_date": (
                prediction.latest_validation_date
            ),
            "feature_schema_version": (
                prediction.feature_schema_version
            ),
        },
    }

    inserted = repository.save_record(record)

    return PredictionJobResult(
        record=record,
        inserted=inserted,
        processed_file=processed_file,
    )


def _load_latest_feature_row(
    processed_directory: Path,
    feature_columns: list[str],
    official_time: datetime,
) -> tuple[dict[str, object], datetime, Path]:
    processed_files = list(
        processed_directory.glob(
            "weather_hourly_*.csv"
        )
    )

    if not processed_files:
        raise PredictionJobError(
            f"Tidak ada processed file di "
            f"{processed_directory}."
        )

    processed_file = max(
        processed_files,
        key=lambda path: path.stat().st_mtime,
    )

    try:
        data = pd.read_csv(processed_file)
    except (OSError, pd.errors.ParserError) as exc:
        raise PredictionJobError(
            f"Processed file tidak dapat dibaca: {exc}"
        ) from exc

    required_columns = {
        "event_time_utc",
        *feature_columns,
    }
    missing_columns = required_columns.difference(
        data.columns
    )

    if missing_columns:
        raise PredictionJobError(
            f"Processed file kehilangan kolom: "
            f"{sorted(missing_columns)}"
        )

    data["event_time_utc"] = pd.to_datetime(
        data["event_time_utc"],
        utc=True,
        errors="coerce",
    )

    candidates = data.loc[
        data["event_time_utc"].notna()
        & (data["event_time_utc"] <= official_time)
        & data[feature_columns].notna().all(axis=1)
    ].copy()

    if candidates.empty:
        raise PredictionJobError(
            "Tidak ada baris fitur yang siap untuk inference."
        )

    candidates = candidates.sort_values(
        "event_time_utc",
        kind="stable",
    )

    if candidates["event_time_utc"].duplicated().any():
        raise PredictionJobError(
            "Processed file memiliki timestamp duplikat."
        )

    latest_row = candidates.iloc[-1]
    feature_timestamp = latest_row[
        "event_time_utc"
    ].to_pydatetime()

    if (
        official_time - feature_timestamp
        > timedelta(hours=6)
    ):
        raise PredictionJobError(
            "Fitur terbaru berusia lebih dari enam jam."
        )

    feature_values = {
        column: latest_row[column]
        for column in feature_columns
    }

    return (
        feature_values,
        feature_timestamp,
        processed_file,
    )


def _risk_level(probability: float) -> str:
    if probability < 0.3:
        return "low"
    if probability < 0.7:
        return "moderate"
    return "high"


def _preparation_action(risk_level: str) -> str:
    actions = {
        "low": (
            "Tidak diperlukan persiapan khusus "
            "terkait hujan."
        ),
        "moderate": (
            "Bawa perlindungan hujan dan periksa "
            "kesiapan lokasi cadangan."
        ),
        "high": (
            "Siapkan perlengkapan hujan dan "
            "lokasi cadangan."
        ),
    }
    return actions[risk_level]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Membuat prediksi risiko hujan "
            "untuk slot waktu saat ini."
        )
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            os.getenv(
                "RAIN_MODEL_DIR",
                "models/rain-baseline-v1",
            )
        ),
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed"),
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(
            os.getenv(
                "RAIN_PREDICTION_DB_PATH",
                "data/predictions/predictions.db",
            )
        ),
    )
    return parser.parse_args()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return (
            value.astimezone(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

    if isinstance(value, Path):
        return str(value)

    raise TypeError(
        f"Tipe {type(value).__name__} "
        "tidak dapat diserialisasi."
    )


def main() -> None:
    arguments = parse_arguments()

    predictor = RainModelPredictor(
        arguments.model_dir
    )
    repository = SQLitePredictionRepository(
        arguments.database_path
    )

    result = run_prediction_job(
        predictor=predictor,
        repository=repository,
        processed_directory=(
            arguments.processed_dir
        ),
        generated_at=datetime.now(UTC),
    )

    print("Prediction job berhasil.")
    print(f"Processed file: {result.processed_file}")
    print(f"Inserted      : {result.inserted}")
    print(
        json.dumps(
            result.record,
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        )
    )


if __name__ == "__main__":
    main()