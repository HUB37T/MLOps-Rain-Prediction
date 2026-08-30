from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rain_prediction.api.main import create_app


class FixedClock:
    def __init__(self, current_time: datetime) -> None:
        self.current_time = current_time

    def now(self) -> datetime:
        return self.current_time


def test_current_prediction_returns_the_dashboard_contract() -> None:
    client = TestClient(
        create_app(clock=FixedClock(datetime(2026, 8, 30, 7, 5, tzinfo=UTC)))
    )

    response = client.get("/api/v1/predictions/current")

    assert response.status_code == 200
    assert response.json() == {
        "server_time": "2026-08-30T07:05:00Z",
        "primary_location": {
            "id": "filkom-ub",
            "name": "FILKOM Universitas Brawijaya",
            "requested_coordinate": {"latitude": -7.9666, "longitude": 112.6326},
            "resolved_grid": {"latitude": -7.9666, "longitude": 112.6326},
        },
        "status": "available",
        "active_configuration": {
            "decision_threshold": 0.5,
            "risk_configuration_version": "risk-v1",
        },
        "prediction": {
            "prediction_record_id": "pred-2026-08-30T07:00:00Z",
            "official_prediction_time": "2026-08-30T07:00:00Z",
            "actual_generation_time": "2026-08-30T07:05:00Z",
            "prediction_horizon": {
                "start": "2026-08-30T08:00:00Z",
                "end": "2026-08-30T11:00:00Z",
            },
            "rain_probability": 0.499,
            "predicted_class": "no_rain",
            "decision_threshold": 0.5,
            "near_threshold": True,
            "risk_level": "moderate",
            "risk_boundaries": {
                "low_to_moderate": 0.3,
                "moderate_to_high": 0.7,
            },
            "risk_configuration_version": "risk-v1",
            "preparation_action": "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
            "preparation_copy_version": "prep-v1",
            "feature_timestamp": "2026-08-30T07:00:00Z",
            "data_freshness_seconds": 300,
            "freshness_status": "fresh",
            "model": {
                "name": "baseline",
                "version": "baseline-v1",
                "status": "experimental",
                "latest_validation_date": "2026-08-29",
            },
        },
        "warnings": [],
    }
