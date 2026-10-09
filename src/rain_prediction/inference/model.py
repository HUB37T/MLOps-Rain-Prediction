from __future__ import annotations

from importlib import metadata
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import joblib
import pandas as pd


class ModelArtifactError(RuntimeError):
    """Raised when a model artifact is missing or invalid."""


class ModelInputError(ValueError):
    """Raised when feature input cannot safely enter the model."""


class ModelInferenceError(RuntimeError):
    """Raised when the model cannot produce a valid probability."""


@dataclass(frozen=True)
class RainPrediction:
    probability: float
    predicted_class: str
    decision_threshold: float
    near_threshold: bool
    model_name: str
    model_version: str
    feature_schema_version: str
    latest_validation_date: str


class RainModelPredictor:
    """Load one model artifact and perform validated inference."""

    def __init__(self, artifact_directory: Path) -> None:
        self._artifact_directory = artifact_directory
        self._model_path = artifact_directory / "model.joblib"
        self._metadata_path = artifact_directory / "metadata.json"

        self._model = None
        self._feature_columns: list[str] = []
        self._decision_threshold = 0.5
        self._feature_schema_version = ""
        self._model_name = ""
        self._model_version = ""
        self._latest_validation_date = ""

        self._load_artifact()

    @property
    def feature_columns(self) -> tuple[str, ...]:
        return tuple(self._feature_columns)

    @property
    def decision_threshold(self) -> float:
        return self._decision_threshold

    def _load_artifact(self) -> None:
        if not self._model_path.is_file():
            raise ModelArtifactError(
                f"Model tidak ditemukan: {self._model_path}"
            )

        if not self._metadata_path.is_file():
            raise ModelArtifactError(
                f"Metadata tidak ditemukan: {self._metadata_path}"
            )

        try:
            bundle = joblib.load(self._model_path)
        except Exception as exc:
            raise ModelArtifactError(
                f"Model tidak dapat dimuat: {exc}"
            ) from exc

        try:
            metadata = json.loads(
                self._metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelArtifactError(
                f"Metadata tidak dapat dibaca: {exc}"
            ) from exc

        if not isinstance(bundle, dict):
            raise ModelArtifactError(
                "Model bundle harus berupa dictionary."
            )

        required_keys = {
            "model",
            "feature_columns",
            "decision_threshold",
            "target_column",
            "feature_schema_version",
        }
        missing_keys = required_keys.difference(bundle)

        if missing_keys:
            raise ModelArtifactError(
                f"Model bundle tidak lengkap: {sorted(missing_keys)}"
            )

        feature_columns = bundle["feature_columns"]

        if (
            not isinstance(feature_columns, list)
            or not feature_columns
            or not all(
                isinstance(column, str) and column
                for column in feature_columns
            )
        ):
            raise ModelArtifactError(
                "Daftar feature_columns tidak valid."
            )

        if len(feature_columns) != len(set(feature_columns)):
            raise ModelArtifactError(
                "Daftar feature_columns memiliki duplikat."
            )

        threshold = bundle["decision_threshold"]

        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0 <= float(threshold) <= 1
        ):
            raise ModelArtifactError(
                "Decision threshold model tidak valid."
            )

        model = bundle["model"]

        if not callable(getattr(model, "predict_proba", None)):
            raise ModelArtifactError(
                "Model tidak mendukung predict_proba."
            )

        bundle_schema = bundle["feature_schema_version"]
        metadata_schema = metadata.get("feature_schema_version")

        if bundle_schema != metadata_schema:
            raise ModelArtifactError(
                "Feature schema model dan metadata berbeda."
            )

        model_name = metadata.get("model_type")
        model_version = metadata.get("run_id")

        if not isinstance(model_name, str) or not model_name:
            raise ModelArtifactError(
                "Metadata model_type tidak valid."
            )

        if not isinstance(model_version, str) or not model_version:
            raise ModelArtifactError(
                "Metadata run_id tidak valid."
            )

        latest_validation_date = metadata.get(
            "latest_validation_date"
        )

        if not isinstance(latest_validation_date, str):
            test_metadata = metadata.get("test")

            if isinstance(test_metadata, dict):
                latest_validation_date = test_metadata.get(
                    "end_time_utc"
                )

        if not isinstance(latest_validation_date, str):
            test_period = metadata.get("test_period")

            if (
                isinstance(test_period, str)
                and " through " in test_period
            ):
                latest_validation_date = (
                    test_period
                    .rsplit(" through ", maxsplit=1)[-1]
                    .strip()
                )

        if not latest_validation_date:
            raise ModelArtifactError(
                "Tanggal evaluasi model tidak tersedia."
            )
        self._model = model
        self._feature_columns = feature_columns
        self._decision_threshold = float(threshold)
        self._feature_schema_version = str(bundle_schema)
        self._model_name = model_name
        self._model_version = model_version
        self._latest_validation_date = latest_validation_date

    def predict(
        self,
        feature_values: Mapping[str, object],
    ) -> RainPrediction:
        missing_features = [
            column
            for column in self._feature_columns
            if column not in feature_values
        ]

        if missing_features:
            raise ModelInputError(
                f"Fitur tidak lengkap: {missing_features}"
            )

        numeric_values: list[float] = []

        for column in self._feature_columns:
            value = feature_values[column]

            if isinstance(value, bool):
                numeric_value = float(value)
            else:
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ModelInputError(
                        f"Fitur {column!r} bukan angka valid."
                    ) from exc

            if not math.isfinite(numeric_value):
                raise ModelInputError(
                    f"Fitur {column!r} tidak finite."
                )

            numeric_values.append(numeric_value)

        model_input = pd.DataFrame(
            [numeric_values],
            columns=self._feature_columns,
        )

        try:
            probabilities = self._model.predict_proba(
                model_input
            )
            classes = list(self._model.classes_)
            positive_index = classes.index(1)
            probability = float(
                probabilities[0][positive_index]
            )
        except Exception as exc:
            raise ModelInferenceError(
                f"Inference model gagal: {exc}"
            ) from exc

        if not math.isfinite(probability):
            raise ModelInferenceError(
                "Model menghasilkan probabilitas non-finite."
            )

        if not 0 <= probability <= 1:
            raise ModelInferenceError(
                "Probabilitas model berada di luar 0–1."
            )

        predicted_class = (
            "rain"
            if probability >= self._decision_threshold
            else "no_rain"
        )

        return RainPrediction(
            probability=probability,
            predicted_class=predicted_class,
            decision_threshold=self._decision_threshold,
            near_threshold=(
                abs(
                    probability
                    - self._decision_threshold
                )
                <= 0.05
            ),
            model_name=self._model_name,
            model_version=self._model_version,
            feature_schema_version=(
                self._feature_schema_version
            ),
            latest_validation_date=(
                self._latest_validation_date
            ),
        )