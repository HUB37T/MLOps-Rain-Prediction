"""Promotion must never succeed with missing, non-finite or poor metrics."""
import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rain_prediction.training.evaluate_and_register import evaluate, validation_errors


POLICY = {"minimum_validation_pr_auc": 0.90, "minimum_validation_f1": 0.82}


@pytest.mark.parametrize("metrics", [
    {"validation_pr_auc": 0.90, "validation_f1": 0.82},
    {"validation_pr_auc": 0.95, "validation_f1": 0.86},
])
def test_metrics_at_or_above_limits_pass(metrics):
    assert validation_errors(metrics, POLICY) == []


@pytest.mark.parametrize("value", [0.89, None, math.nan, math.inf, -1, 1.1, True])
def test_unusable_auc_is_rejected(value):
    assert validation_errors({"validation_pr_auc": value, "validation_f1": 0.85}, POLICY)


def test_low_f1_is_rejected_even_with_good_auc():
    assert validation_errors({"validation_pr_auc": 0.95, "validation_f1": 0.81}, POLICY)


def test_missing_metric_is_rejected():
    assert validation_errors({"validation_f1": 0.85}, POLICY)


def test_invalid_threshold_is_rejected():
    assert validation_errors({"validation_pr_auc": 0.95, "validation_f1": 0.85}, {})


def test_failed_gate_never_calls_registry_and_writes_failure_report(tmp_path):
    client = Mock()
    client.get_run.return_value = SimpleNamespace(
        info=SimpleNamespace(status="FINISHED"),
        data=SimpleNamespace(metrics={"validation_pr_auc": 0.5, "validation_f1": 0.7}),
    )
    report = tmp_path / "report.json"
    with pytest.raises(ValueError, match="validation_pr_auc"):
        evaluate({"run_id": "bad-run"}, POLICY, report,
                 "sqlite:///unused.db", "test-sha", register=True, client=client)
    client.search_model_versions.assert_not_called()
    client.transition_model_version_stage.assert_not_called()
    assert '"passed": false' in report.read_text()


def test_unfinished_run_cannot_be_registered(tmp_path):
    client = Mock()
    client.get_run.return_value = SimpleNamespace(
        info=SimpleNamespace(status="RUNNING"),
        data=SimpleNamespace(metrics={"validation_pr_auc": 0.95, "validation_f1": 0.85}),
    )
    with pytest.raises(ValueError, match="not FINISHED"):
        evaluate({"run_id": "incomplete"}, POLICY, tmp_path / "report.json",
                 "sqlite:///unused.db", "test-sha", register=True, client=client)
    client.transition_model_version_stage.assert_not_called()


def test_model_from_another_run_cannot_be_registered(tmp_path, monkeypatch):
    import mlflow
    client = Mock()
    client.get_run.return_value = SimpleNamespace(
        info=SimpleNamespace(status="FINISHED"),
        data=SimpleNamespace(metrics={"validation_pr_auc": 0.95, "validation_f1": 0.85}),
    )
    monkeypatch.setattr(mlflow, "get_logged_model", lambda _: SimpleNamespace(source_run_id="other"))
    with pytest.raises(ValueError, match="does not belong"):
        evaluate({"run_id": "selected", "model_uri": "models:/m-other"}, POLICY,
                 tmp_path / "report.json", "sqlite:///unused.db", "test-sha",
                 register=True, client=client)
    client.transition_model_version_stage.assert_not_called()
