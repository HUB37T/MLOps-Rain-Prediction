from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from rain_prediction.api.main import create_app


class FixedClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def now(self) -> datetime:
        return self.current_time


class StaticPredictionRepository:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def list_records(self) -> list[dict[str, object]]:
        return self.records


SERVER_TIME = datetime(2026, 8, 30, 7, 5, tzinfo=UTC)


def prediction_record(
    official_time: datetime,
    *,
    feature_timestamp: datetime | None = None,
    actual_generation_time: datetime | None = None,
    rain_probability: float = 0.499,
    decision_threshold: float = 0.5,
) -> dict[str, object]:
    feature_timestamp = feature_timestamp or official_time
    actual_generation_time = actual_generation_time or official_time + timedelta(minutes=5)
    risk_level = "low" if rain_probability < 0.3 else "high" if rain_probability >= 0.7 else "moderate"
    return {
        "prediction_record_id": f"pred-{official_time.isoformat()}",
        "official_prediction_time": official_time,
        "actual_generation_time": actual_generation_time,
        "prediction_horizon": {
            "start": official_time + timedelta(hours=1),
            "end": official_time + timedelta(hours=4),
        },
        "rain_probability": rain_probability,
        "predicted_class": "rain" if rain_probability >= decision_threshold else "no_rain",
        "decision_threshold": decision_threshold,
        "near_threshold": abs(rain_probability - decision_threshold) <= 0.05,
        "risk_level": risk_level,
        "risk_boundaries": {"low_to_moderate": 0.3, "moderate_to_high": 0.7},
        "risk_configuration_version": "risk-v1",
        "preparation_action": {
            "low": "Tidak diperlukan persiapan khusus terkait hujan.",
            "moderate": "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
            "high": "Siapkan perlengkapan hujan dan lokasi cadangan.",
        }[risk_level],
        "preparation_copy_version": "prep-v1",
        "feature_timestamp": feature_timestamp,
        "model": {
            "name": "baseline",
            "version": "baseline-v1",
            "status": "experimental",
            "latest_validation_date": "2026-08-29",
        },
    }


def get_prediction(
    server_time: datetime,
    records: list[dict[str, object]],
) -> dict[str, object]:
    client = TestClient(
        create_app(
            clock=FixedClock(server_time),
            prediction_repository=StaticPredictionRepository(records),
        )
    )
    return client.get("/api/v1/predictions/current").json()


def test_prediction_is_fresh_at_exactly_two_hours() -> None:
    official_time = datetime(2026, 8, 30, 5, 0, tzinfo=UTC)

    body = get_prediction(
        datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
        [prediction_record(official_time, feature_timestamp=datetime(2026, 8, 30, 5, 0, tzinfo=UTC))],
    )

    assert body["status"] == "available"
    assert body["prediction"]["freshness_status"] == "fresh"
    assert body["prediction"]["data_freshness_seconds"] == 7200


def test_prediction_is_stale_after_two_hours_and_available_at_six_hours() -> None:
    official_time = datetime(2026, 8, 30, 4, 0, tzinfo=UTC)

    body = get_prediction(
        datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
        [prediction_record(official_time, feature_timestamp=datetime(2026, 8, 30, 1, 0, tzinfo=UTC))],
    )

    assert body["status"] == "available"
    assert body["prediction"]["freshness_status"] == "stale"
    assert body["prediction"]["data_freshness_seconds"] == 21600


def test_prediction_is_unavailable_after_six_hours() -> None:
    official_time = datetime(2026, 8, 30, 4, 0, tzinfo=UTC)

    body = get_prediction(
        datetime(2026, 8, 30, 7, 10, 1, tzinfo=UTC),
        [prediction_record(official_time, feature_timestamp=datetime(2026, 8, 30, 0, 0, tzinfo=UTC))],
    )

    assert body["status"] == "unavailable"
    assert body["prediction"] is None


def test_prediction_horizon_is_valid_at_start_and_ended_at_exact_end() -> None:
    official_time = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)
    record = prediction_record(official_time)

    at_start = get_prediction(datetime(2026, 8, 30, 7, 0, tzinfo=UTC), [record])
    at_end = get_prediction(datetime(2026, 8, 30, 10, 10, tzinfo=UTC), [record])

    assert at_start["prediction"]["prediction_record_id"] == record["prediction_record_id"]
    assert at_end["status"] == "unavailable"


def test_record_is_usable_until_grace_deadline_but_not_at_deadline() -> None:
    official_time = datetime(2026, 8, 30, 7, 0, tzinfo=UTC)
    before_deadline = prediction_record(
        official_time,
        actual_generation_time=datetime(2026, 8, 30, 7, 9, 59, tzinfo=UTC),
    )
    at_deadline = prediction_record(
        official_time,
        actual_generation_time=datetime(2026, 8, 30, 7, 10, tzinfo=UTC),
    )

    assert get_prediction(datetime(2026, 8, 30, 7, 9, 59, tzinfo=UTC), [before_deadline])["status"] == "available"
    assert get_prediction(datetime(2026, 8, 30, 7, 10, tzinfo=UTC), [at_deadline])["status"] == "unavailable"


def test_newest_usable_record_wins() -> None:
    older = prediction_record(datetime(2026, 8, 30, 6, 0, tzinfo=UTC), rain_probability=0.2)
    newer = prediction_record(datetime(2026, 8, 30, 7, 0, tzinfo=UTC), rain_probability=0.8)

    body = get_prediction(SERVER_TIME, [older, newer])

    assert body["prediction"]["prediction_record_id"] == newer["prediction_record_id"]
    assert body["prediction"]["rain_probability"] == 0.8
    assert body["prediction"]["risk_level"] == "high"


def test_invalid_newer_record_falls_back_without_recalculating_older_metadata() -> None:
    fallback = prediction_record(
        datetime(2026, 8, 30, 6, 0, tzinfo=UTC),
        rain_probability=0.499,
        decision_threshold=0.55,
    )
    invalid_newer = prediction_record(datetime(2026, 8, 30, 7, 0, tzinfo=UTC))
    invalid_newer["predicted_class"] = "rain"

    body = get_prediction(SERVER_TIME, [fallback, invalid_newer])

    assert body["status"] == "available"
    assert body["prediction"]["prediction_record_id"] == fallback["prediction_record_id"]
    assert body["prediction"]["decision_threshold"] == 0.55
    assert body["prediction"]["rain_probability"] == 0.499
    assert body["prediction"]["predicted_class"] == "no_rain"
    assert body["prediction"]["risk_level"] == "moderate"
    assert body["warnings"][0]["code"] == "prediction_fallback"
    assert body["warnings"][0]["failed_official_prediction_time"] == "2026-08-30T07:00:00Z"
    assert body["warnings"][0]["fallback_official_prediction_time"] == "2026-08-30T06:00:00Z"


def test_pending_response_has_no_prediction_values() -> None:
    body = get_prediction(SERVER_TIME, [])

    assert body["status"] == "pending"
    assert body["prediction"] is None
    assert body["warnings"] == [
        {
            "code": "prediction_pending",
            "message": "Prediksi sedang disiapkan.",
            "official_prediction_time": "2026-08-30T07:00:00Z",
        }
    ]
