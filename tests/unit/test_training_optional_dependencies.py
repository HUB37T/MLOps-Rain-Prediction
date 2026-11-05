"""CPU-only automated training must not require optional boosting libraries."""
import builtins
import importlib
import sys
from types import SimpleNamespace


def test_random_forest_without_boosting_dependencies(monkeypatch):
    original_import = builtins.__import__

    def without_boosting(name, *args, **kwargs):
        if name.split(".")[0] in {"xgboost", "lightgbm"}:
            raise ImportError("Optional boosting library deliberately unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_boosting)
    monkeypatch.delitem(sys.modules, "rain_prediction.training.train", raising=False)
    train = importlib.import_module("rain_prediction.training.train")
    model = train.create_model(SimpleNamespace(
        model="random_forest", class_weight="balanced", n_estimators=5,
        max_depth=3, min_samples_leaf=2, max_features="sqrt", random_state=42,
    ))
    assert type(model).__name__ == "RandomForestClassifier"
