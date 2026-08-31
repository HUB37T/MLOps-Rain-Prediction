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
    rain_probability: float = 0.499,
    actual_generation_time: datetime | None = None,
) -> dict[str, object]:
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
        "predicted_class": "rain" if rain_probability >= 0.5 else "no_rain",
        "decision_threshold": 0.5,
        "near_threshold": abs(rain_probability - 0.5) <= 0.05,
        "risk_level": risk_level,
        "risk_boundaries": {"low_to_moderate": 0.3, "moderate_to_high": 0.7},
        "risk_configuration_version": "risk-v1",
        "preparation_action": {
            "low": "Tidak diperlukan persiapan khusus terkait hujan.",
            "moderate": "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
            "high": "Siapkan perlengkapan hujan dan lokasi cadangan.",
        }[risk_level],
        "preparation_copy_version": "prep-v1",
        "feature_timestamp": official_time,
        "model": {
            "name": "baseline",
            "version": "baseline-v1",
            "status": "experimental",
            "latest_validation_date": "2026-08-29",
        },
    }


def get_history(
    server_time: datetime,
    records: list[dict[str, object]],
    query: str = "?slots=24",
):
    client = TestClient(
        create_app(
            clock=FixedClock(server_time),
            prediction_repository=StaticPredictionRepository(records),
        )
    )
    return client.get(f"/api/v1/predictions/history{query}")


def test_history_returns_24_fixed_slots_ending_with_current_scheduled_slot() -> None:
    records = [
        prediction_record(datetime(2026, 8, 30, 6, 0, tzinfo=UTC), rain_probability=0.2),
        prediction_record(datetime(2026, 8, 30, 5, 0, tzinfo=UTC), rain_probability=0.8),
    ]

    response = get_history(SERVER_TIME, records)

    assert response.status_code == 200
    body = response.json()
    assert body["server_time"] == "2026-08-30T07:05:00Z"
    assert body["slot_count"] == 24
    assert len(body["slots"]) == 24
    assert body["slots"][0]["official_prediction_time"] == "2026-08-30T07:00:00Z"
    assert body["slots"][0]["status"] == "pending"
    assert body["slots"][1]["official_prediction_time"] == "2026-08-30T06:00:00Z"
    assert body["slots"][1]["status"] == "issued"
    assert body["slots"][1]["prediction"]["rain_probability"] == 0.2
    assert body["slots"][2]["status"] == "issued"
    assert body["slots"][3]["official_prediction_time"] == "2026-08-30T04:00:00Z"
    assert body["slots"][3]["status"] == "unavailable"
    assert body["slots"][3]["prediction"] is None
    assert body["slots"][-1]["official_prediction_time"] == "2026-08-29T08:00:00Z"


def test_history_marks_current_slot_unavailable_after_grace_period() -> None:
    response = get_history(datetime(2026, 8, 30, 7, 10, tzinfo=UTC), [])

    body = response.json()

    assert body["slots"][0] == {
        "official_prediction_time": "2026-08-30T07:00:00Z",
        "status": "unavailable",
        "prediction": None,
    }


def test_history_quarantines_invalid_record_as_failed_without_zero_values() -> None:
    invalid_record = prediction_record(datetime(2026, 8, 30, 6, 0, tzinfo=UTC))
    invalid_record["predicted_class"] = "rain"

    body = get_history(SERVER_TIME, [invalid_record]).json()

    assert body["slots"][1] == {
        "official_prediction_time": "2026-08-30T06:00:00Z",
        "status": "failed",
        "prediction": None,
    }


def test_history_requires_the_approved_24_slot_window() -> None:
    response = get_history(SERVER_TIME, [], query="?slots=12")

    assert response.status_code == 422
