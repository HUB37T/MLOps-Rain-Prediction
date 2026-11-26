"""Serving must use an unambiguous Production model and its actual feature schema."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    "prepare_model_serving", Path(__file__).resolve().parents[2] / "scripts/prepare_model_serving.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def version(number, stage, status="READY"):
    return SimpleNamespace(version=number, current_stage=stage, status=status)


def test_export_uses_production_instead_of_newest_staging():
    production = version(2, "Production")
    assert module.select_production([production, version(3, "Staging")]) is production


@pytest.mark.parametrize("versions", [[], [version(1, "Staging")],
                                     [version(1, "Production", "PENDING_REGISTRATION")],
                                     [version(1, "Production"), version(2, "Production")]])
def test_ambiguous_or_unready_production_is_rejected(versions):
    with pytest.raises(ValueError, match="exactly one"):
        module.select_production(versions)


def test_payload_follows_model_signature_and_excludes_target():
    frame = pd.DataFrame({"rain": [1.0], "target_rain_next_3h": [1], "humidity": [95.0]})
    assert module.make_payload(frame, ["humidity", "rain"]) == {
        "dataframe_split": {"columns": ["humidity", "rain"], "data": [[95.0, 1.0]]}}


@pytest.mark.parametrize("frame", [pd.DataFrame({"rain": [1.0]}),
                                  pd.DataFrame({"rain": [float("nan")], "humidity": [90.0]}),
                                  pd.DataFrame({"rain": [1.0], "humidity": [float("inf")]})])
def test_incomplete_or_nonfinite_input_is_rejected(frame):
    with pytest.raises(ValueError):
        module.make_payload(frame, ["humidity", "rain"])
