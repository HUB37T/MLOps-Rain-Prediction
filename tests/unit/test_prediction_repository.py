from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from rain_prediction.inference.repository import (
    SQLitePredictionRepository,
)


def prediction_record() -> dict[str, object]:
    official_time = datetime(
        2026,
        10,
        9,
        7,
        0,
        tzinfo=UTC,
    )

    return {
        "prediction_record_id": "pred-20261009T070000Z",
        "official_prediction_time": official_time,
        "actual_generation_time": (
            official_time + timedelta(minutes=5)
        ),
        "prediction_horizon": {
            "start": official_time + timedelta(hours=1),
            "end": official_time + timedelta(hours=4),
        },
        "rain_probability": 0.62,
        "predicted_class": "rain",
        "decision_threshold": 0.2867,
        "near_threshold": False,
        "risk_level": "moderate",
        "risk_boundaries": {
            "low_to_moderate": 0.3,
            "moderate_to_high": 0.7,
        },
        "risk_configuration_version": "risk-v1",
        "preparation_action": (
            "Bawa perlindungan hujan dan periksa "
            "kesiapan lokasi cadangan."
        ),
        "preparation_copy_version": "prep-v1",
        "feature_timestamp": official_time,
        "model": {
            "name": "logistic_regression",
            "version": "20261009T105720Z",
            "status": "experimental",
            "latest_validation_date": "2026-09-30",
        },
    }


def test_repository_saves_and_reads_record(
    tmp_path: Path,
) -> None:
    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )
    expected = prediction_record()

    inserted = repository.save_record(expected)
    records = repository.list_records()

    assert inserted is True
    assert len(records) == 1
    assert records[0] == expected


def test_repository_does_not_replace_duplicate_record(
    tmp_path: Path,
) -> None:
    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )
    record = prediction_record()

    first_insert = repository.save_record(record)
    second_insert = repository.save_record(record)

    assert first_insert is True
    assert second_insert is False
    assert len(repository.list_records()) == 1


def test_repository_orders_newest_record_first(
    tmp_path: Path,
) -> None:
    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )

    older = prediction_record()
    newer = prediction_record()

    newer_time = (
        older["official_prediction_time"]
        + timedelta(hours=1)
    )
    newer["prediction_record_id"] = (
        "pred-20261009T080000Z"
    )
    newer["official_prediction_time"] = newer_time
    newer["actual_generation_time"] = (
        newer_time + timedelta(minutes=5)
    )
    newer["feature_timestamp"] = newer_time
    newer["prediction_horizon"] = {
        "start": newer_time + timedelta(hours=1),
        "end": newer_time + timedelta(hours=4),
    }

    repository.save_record(older)
    repository.save_record(newer)

    records = repository.list_records()

    assert records[0]["prediction_record_id"] == (
        "pred-20261009T080000Z"
    )
    assert records[1]["prediction_record_id"] == (
        "pred-20261009T070000Z"
    )