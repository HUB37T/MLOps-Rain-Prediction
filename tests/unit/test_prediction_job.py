from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from rain_prediction.inference.job import (
    PredictionJobError,
    run_prediction_job,
)
from rain_prediction.inference.model import (
    RainPrediction,
)
from rain_prediction.inference.repository import (
    SQLitePredictionRepository,
)
from rain_prediction.inference.lifecycle import (
    resolve_current_prediction,
)


class FakePredictor:
    @property
    def feature_columns(self) -> tuple[str, ...]:
        return ("temperature", "humidity")

    def predict(
        self,
        feature_values: dict[str, object],
    ) -> RainPrediction:
        assert feature_values == {
            "temperature": 27.0,
            "humidity": 88.0,
        }

        return RainPrediction(
            probability=0.62,
            predicted_class="rain",
            decision_threshold=0.2867,
            near_threshold=False,
            model_name="logistic_regression",
            model_version="baseline-v1",
            feature_schema_version=(
                "weather-rain-3h-features-v2"
            ),
            latest_validation_date="2026-09-30",
        )


def write_processed_file(
    directory: Path,
    event_time: str,
) -> Path:
    directory.mkdir(parents=True)

    output_path = (
        directory / "weather_hourly_test.csv"
    )

    pd.DataFrame(
        [
            {
                "event_time_utc": event_time,
                "temperature": 27.0,
                "humidity": 88.0,
            }
        ]
    ).to_csv(output_path, index=False)

    return output_path


def test_job_generates_record_usable_by_api(
    tmp_path: Path,
) -> None:
    processed_directory = tmp_path / "processed"
    write_processed_file(
        processed_directory,
        "2026-10-09T07:00:00Z",
    )

    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )
    generated_at = datetime(
        2026,
        10,
        9,
        7,
        5,
        tzinfo=UTC,
    )

    result = run_prediction_job(
        predictor=FakePredictor(),
        repository=repository,
        processed_directory=processed_directory,
        generated_at=generated_at,
    )

    response = resolve_current_prediction(
        repository,
        generated_at,
    )

    assert result.inserted is True
    assert response["status"] == "available"
    assert response["prediction"][
        "rain_probability"
    ] == 0.62
    assert response["prediction"][
        "predicted_class"
    ] == "rain"


def test_job_is_idempotent_for_same_hour(
    tmp_path: Path,
) -> None:
    processed_directory = tmp_path / "processed"
    write_processed_file(
        processed_directory,
        "2026-10-09T07:00:00Z",
    )

    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )
    generated_at = datetime(
        2026,
        10,
        9,
        7,
        5,
        tzinfo=UTC,
    )

    first = run_prediction_job(
        predictor=FakePredictor(),
        repository=repository,
        processed_directory=processed_directory,
        generated_at=generated_at,
    )
    second = run_prediction_job(
        predictor=FakePredictor(),
        repository=repository,
        processed_directory=processed_directory,
        generated_at=generated_at,
    )

    assert first.inserted is True
    assert second.inserted is False
    assert len(repository.list_records()) == 1


def test_job_rejects_late_generation(
    tmp_path: Path,
) -> None:
    processed_directory = tmp_path / "processed"
    write_processed_file(
        processed_directory,
        "2026-10-09T07:00:00Z",
    )

    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )

    with pytest.raises(
        PredictionJobError,
        match="sebelum menit ke-10",
    ):
        run_prediction_job(
            predictor=FakePredictor(),
            repository=repository,
            processed_directory=(
                processed_directory
            ),
            generated_at=datetime(
                2026,
                10,
                9,
                7,
                10,
                tzinfo=UTC,
            ),
        )


def test_job_rejects_stale_features(
    tmp_path: Path,
) -> None:
    processed_directory = tmp_path / "processed"
    write_processed_file(
        processed_directory,
        "2026-10-09T00:00:00Z",
    )

    repository = SQLitePredictionRepository(
        tmp_path / "predictions.db"
    )

    with pytest.raises(
        PredictionJobError,
        match="lebih dari enam jam",
    ):
        run_prediction_job(
            predictor=FakePredictor(),
            repository=repository,
            processed_directory=(
                processed_directory
            ),
            generated_at=datetime(
                2026,
                10,
                9,
                7,
                5,
                tzinfo=UTC,
            ),
        )