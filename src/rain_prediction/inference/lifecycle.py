from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Protocol


class PredictionRepository(Protocol):
    def list_records(self) -> list[dict[str, object]]:
        """Return stored Prediction Records for the Primary Location."""


class Predictor(Protocol):
    def rain_probability(self) -> float:
        """Return an unrounded Rain Probability."""


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""


class MockPredictionRepository:
    def __init__(self, clock: Clock, predictor: Predictor) -> None:
        self._clock = clock
        self._predictor = predictor

    def list_records(self) -> list[dict[str, object]]:
        server_time = self._clock.now().astimezone(UTC)
        official_time = server_time.replace(minute=0, second=0, microsecond=0)
        probability = self._predictor.rain_probability()
        risk_level = _risk_level(probability)
        return [
            {
                "prediction_record_id": f"pred-{_utc_timestamp(official_time)}",
                "official_prediction_time": official_time,
                "actual_generation_time": server_time,
                "prediction_horizon": {
                    "start": official_time + timedelta(hours=1),
                    "end": official_time + timedelta(hours=4),
                },
                "rain_probability": probability,
                "predicted_class": "rain" if probability >= 0.5 else "no_rain",
                "decision_threshold": 0.5,
                "near_threshold": abs(probability - 0.5) <= 0.05,
                "risk_level": risk_level,
                "risk_boundaries": {"low_to_moderate": 0.3, "moderate_to_high": 0.7},
                "risk_configuration_version": "risk-v1",
                "preparation_action": _preparation_action(risk_level),
                "preparation_copy_version": "prep-v1",
                "feature_timestamp": official_time,
                "model": {
                    "name": "baseline",
                    "version": "baseline-v1",
                    "status": "experimental",
                    "latest_validation_date": "2026-08-29",
                },
            }
        ]


def resolve_current_prediction(
    repository: PredictionRepository,
    server_time: datetime,
) -> dict[str, object]:
    server_time = server_time.astimezone(UTC)
    scheduled_time = server_time.replace(minute=0, second=0, microsecond=0)
    records = repository.list_records()
    usable: list[tuple[datetime, dict[str, object]]] = []
    invalid_times: list[datetime] = []

    for record in records:
        official_time = _record_official_time(record)
        if official_time is None or official_time > scheduled_time:
            continue
        if _valid_record(record, server_time):
            usable.append((official_time, record))
        else:
            invalid_times.append(official_time)

    usable.sort(key=lambda item: item[0], reverse=True)
    selected = usable[0] if usable else None
    response: dict[str, object] = {
        "server_time": _utc_timestamp(server_time),
        "primary_location": {
            "id": "filkom-ub",
            "name": "FILKOM Universitas Brawijaya",
            "requested_coordinate": {"latitude": -7.9666, "longitude": 112.6326},
            "resolved_grid": {"latitude": -7.9666, "longitude": 112.6326},
        },
        "active_configuration": {
            "decision_threshold": 0.5,
            "risk_configuration_version": "risk-v1",
        },
    }

    if selected is None:
        if server_time < scheduled_time + timedelta(minutes=10):
            response["status"] = "pending"
            response["warnings"] = [
                {
                    "code": "prediction_pending",
                    "message": "Prediksi sedang disiapkan.",
                    "official_prediction_time": _utc_timestamp(scheduled_time),
                }
            ]
        else:
            response["status"] = "unavailable"
            response["warnings"] = [
                {
                    "code": "prediction_unavailable",
                    "message": "Prediksi untuk periode saat ini belum tersedia.",
                }
            ]
        response["prediction"] = None
        return response

    selected_time, selected_record = selected
    response["status"] = "available"
    response["prediction"] = _prediction_payload(selected_record, server_time)
    warnings: list[dict[str, str]] = []
    prediction = response["prediction"]
    if isinstance(prediction, dict) and prediction["freshness_status"] == "stale":
        warnings.append(
            {
                "code": "prediction_stale",
                "message": "Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan.",
            }
        )
    failed_times = sorted((time for time in invalid_times if time > selected_time), reverse=True)
    if failed_times:
        warnings.append(
            {
                "code": "prediction_fallback",
                "message": "Pembaruan terbaru gagal. Menampilkan prediksi sebelumnya.",
                "failed_official_prediction_time": _utc_timestamp(failed_times[0]),
                "fallback_official_prediction_time": _utc_timestamp(selected_time),
            }
        )
    response["warnings"] = warnings
    return response


def resolve_prediction_history(
    repository: PredictionRepository,
    server_time: datetime,
    slots: int = 24,
) -> dict[str, object]:
    server_time = server_time.astimezone(UTC)
    scheduled_time = server_time.replace(minute=0, second=0, microsecond=0)
    first_slot = scheduled_time - timedelta(hours=slots - 1)
    records_by_slot: dict[datetime, list[dict[str, object]]] = {}
    for record in repository.list_records():
        official_time = _record_official_time(record)
        if official_time is not None and first_slot <= official_time <= scheduled_time:
            records_by_slot.setdefault(official_time, []).append(record)

    history_slots: list[dict[str, object]] = []
    for offset in range(slots):
        official_time = scheduled_time - timedelta(hours=offset)
        matching_records = records_by_slot.get(official_time, [])
        issued_record = next(
            (
                record
                for record in matching_records
                if _valid_record(record, server_time, require_current_window=False)
            ),
            None,
        )
        if issued_record is not None:
            history_slots.append(
                {
                    "official_prediction_time": _utc_timestamp(official_time),
                    "status": "issued",
                    "prediction": _prediction_payload(issued_record, server_time),
                }
            )
        elif official_time == scheduled_time and server_time < scheduled_time + timedelta(minutes=10):
            history_slots.append(
                {
                    "official_prediction_time": _utc_timestamp(official_time),
                    "status": "pending",
                    "prediction": None,
                }
            )
        else:
            history_slots.append(
                {
                    "official_prediction_time": _utc_timestamp(official_time),
                    "status": "failed" if matching_records else "unavailable",
                    "prediction": None,
                }
            )

    return {
        "server_time": _utc_timestamp(server_time),
        "slot_count": slots,
        "slots": history_slots,
    }


def _prediction_payload(record: dict[str, object], server_time: datetime) -> dict[str, object]:
    feature_timestamp = _datetime(record["feature_timestamp"])
    assert feature_timestamp is not None
    freshness_seconds = int((server_time - feature_timestamp).total_seconds())
    payload = dict(record)
    payload["official_prediction_time"] = _utc_timestamp(_datetime(record["official_prediction_time"]))
    payload["actual_generation_time"] = _utc_timestamp(_datetime(record["actual_generation_time"]))
    horizon = record["prediction_horizon"]
    assert isinstance(horizon, dict)
    payload["prediction_horizon"] = {
        "start": _utc_timestamp(_datetime(horizon["start"])),
        "end": _utc_timestamp(_datetime(horizon["end"])),
    }
    payload["feature_timestamp"] = _utc_timestamp(feature_timestamp)
    payload["data_freshness_seconds"] = freshness_seconds
    payload["freshness_status"] = _freshness_status(freshness_seconds)
    return payload


def _valid_record(
    record: dict[str, object],
    server_time: datetime,
    *,
    require_current_window: bool = True,
) -> bool:
    official_time = _record_official_time(record)
    actual_time = _datetime(record.get("actual_generation_time"))
    feature_time = _datetime(record.get("feature_timestamp"))
    horizon = record.get("prediction_horizon")
    if official_time is None or actual_time is None or feature_time is None:
        return False
    if not isinstance(horizon, dict):
        return False
    horizon_start = _datetime(horizon.get("start"))
    horizon_end = _datetime(horizon.get("end"))
    if horizon_start is None or horizon_end is None:
        return False
    if official_time.minute or official_time.second or official_time.microsecond:
        return False
    if actual_time < official_time or actual_time >= official_time + timedelta(minutes=10):
        return False
    if actual_time > server_time or feature_time > official_time:
        return False
    if require_current_window and server_time - feature_time > timedelta(hours=6):
        return False
    if horizon_start != official_time + timedelta(hours=1):
        return False
    if horizon_end != official_time + timedelta(hours=4):
        return False
    if require_current_window and server_time >= horizon_end:
        return False

    probability = record.get("rain_probability")
    threshold = record.get("decision_threshold")
    if not _probability(probability) or not _probability(threshold):
        return False
    predicted_class = record.get("predicted_class")
    if predicted_class not in {"rain", "no_rain"}:
        return False
    if predicted_class != ("rain" if probability >= threshold else "no_rain"):
        return False
    if record.get("near_threshold") != (abs(probability - threshold) <= 0.05):
        return False
    risk_level = record.get("risk_level")
    if risk_level != _risk_level(probability) or not isinstance(risk_level, str):
        return False
    if record.get("risk_boundaries") != {"low_to_moderate": 0.3, "moderate_to_high": 0.7}:
        return False
    if record.get("preparation_action") != _preparation_action(risk_level):
        return False
    required_strings = (
        "prediction_record_id",
        "risk_configuration_version",
        "preparation_copy_version",
    )
    if any(not isinstance(record.get(field), str) for field in required_strings):
        return False
    model = record.get("model")
    return isinstance(model, dict) and {"name", "version", "status", "latest_validation_date"}.issubset(model) and all(
        isinstance(model.get(field), str) for field in model
    )


def _record_official_time(record: dict[str, object]) -> datetime | None:
    return _datetime(record.get("official_prediction_time"))


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(UTC)


def _probability(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def _risk_level(probability: float) -> str:
    if probability < 0.3:
        return "low"
    if probability < 0.7:
        return "moderate"
    return "high"


def _preparation_action(risk_level: object) -> str:
    actions = {
        "low": "Tidak diperlukan persiapan khusus terkait hujan.",
        "moderate": "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
        "high": "Siapkan perlengkapan hujan dan lokasi cadangan.",
    }
    return actions.get(risk_level, "")


def _freshness_status(seconds: int) -> str:
    if seconds <= 2 * 60 * 60:
        return "fresh"
    if seconds <= 6 * 60 * 60:
        return "stale"
    return "unavailable"


def _utc_timestamp(value: datetime | None) -> str:
    assert value is not None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
