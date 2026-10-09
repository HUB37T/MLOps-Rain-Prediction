from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rain_prediction.inference.lifecycle import (
    PredictionServiceError,
)


class SQLitePredictionRepository:
    """Persist and retrieve Prediction Records using SQLite."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize_schema()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prediction_records (
                        prediction_record_id TEXT PRIMARY KEY,
                        official_prediction_time TEXT NOT NULL,
                        actual_generation_time TEXT NOT NULL,
                        feature_timestamp TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        created_at_utc TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_prediction_official_time
                    ON prediction_records (
                        official_prediction_time DESC
                    )
                    """
                )
        except sqlite3.Error as exc:
            raise PredictionServiceError(
                f"Gagal menginisialisasi database: {exc}"
            ) from exc

    def save_record(
        self,
        record: dict[str, object],
    ) -> bool:
        record_id = record.get("prediction_record_id")
        official_time = record.get(
            "official_prediction_time"
        )
        actual_time = record.get(
            "actual_generation_time"
        )
        feature_time = record.get("feature_timestamp")

        if not isinstance(record_id, str) or not record_id:
            raise PredictionServiceError(
                "Prediction Record tidak memiliki ID valid."
            )

        for name, value in (
            ("official_prediction_time", official_time),
            ("actual_generation_time", actual_time),
            ("feature_timestamp", feature_time),
        ):
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
            ):
                raise PredictionServiceError(
                    f"{name} harus berupa datetime timezone-aware."
                )

        try:
            serialized_record = json.dumps(
                record,
                default=_json_default,
                ensure_ascii=False,
                separators=(",", ":"),
            )

            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO prediction_records (
                        prediction_record_id,
                        official_prediction_time,
                        actual_generation_time,
                        feature_timestamp,
                        record_json,
                        created_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(prediction_record_id)
                    DO NOTHING
                    """,
                    (
                        record_id,
                        _utc_timestamp(official_time),
                        _utc_timestamp(actual_time),
                        _utc_timestamp(feature_time),
                        serialized_record,
                        _utc_timestamp(datetime.now(UTC)),
                    ),
                )

                return cursor.rowcount == 1
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise PredictionServiceError(
                f"Gagal menyimpan Prediction Record: {exc}"
            ) from exc

    def list_records(self) -> list[dict[str, object]]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT record_json
                    FROM prediction_records
                    ORDER BY official_prediction_time DESC
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            raise PredictionServiceError(
                f"Gagal membaca Prediction Records: {exc}"
            ) from exc

        records: list[dict[str, object]] = []

        for row in rows:
            try:
                record = json.loads(row["record_json"])
                records.append(
                    _restore_record_datetimes(record)
                )
            except (
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise PredictionServiceError(
                    "Database memiliki Prediction Record "
                    f"yang tidak valid: {exc}"
                ) from exc

        return records


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError(
                "Datetime tanpa timezone tidak dapat disimpan."
            )
        return _utc_timestamp(value)

    raise TypeError(
        f"Nilai {type(value).__name__} tidak dapat diserialisasi."
    )


def _restore_record_datetimes(
    record: dict[str, object],
) -> dict[str, object]:
    restored = dict(record)

    for field in (
        "official_prediction_time",
        "actual_generation_time",
        "feature_timestamp",
    ):
        restored[field] = _parse_datetime(
            restored.get(field)
        )

    horizon = restored.get("prediction_horizon")

    if not isinstance(horizon, dict):
        raise ValueError(
            "prediction_horizon harus berupa object."
        )

    restored["prediction_horizon"] = {
        "start": _parse_datetime(horizon.get("start")),
        "end": _parse_datetime(horizon.get("end")),
    }

    return restored


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp harus berupa string.")

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        raise ValueError("Timestamp harus memiliki timezone.")

    return parsed.astimezone(UTC)


def _utc_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )