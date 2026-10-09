from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data.preprocess import (
    FEATURE_SCHEMA_VERSION,
    RAIN_TARGET_THRESHOLD_MM,
    get_model_feature_columns,
)


TARGET_COLUMN = "target_rain_next_3h"
TIME_COLUMN = "event_time_utc"

PROJECT_TIMEZONE = "Asia/Jakarta"

TRAIN_END = pd.Timestamp(
    "2024-10-01T00:00:00",
    tz=PROJECT_TIMEZONE,
)
VALIDATION_END = pd.Timestamp(
    "2025-10-01T00:00:00",
    tz=PROJECT_TIMEZONE,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Melatih baseline Logistic Regression prediksi hujan."
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed/open_meteo_history"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models/baseline"),
    )
    return parser.parse_args()


def find_latest_processed_file(directory: Path) -> Path:
    files = list(directory.glob("weather_hourly_*.csv"))

    if not files:
        raise FileNotFoundError(
            f"Tidak ditemukan file processed di {directory}."
        )

    return max(files, key=lambda path: path.stat().st_mtime)


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def load_training_data(
    file_path: Path,
    feature_columns: list[str],
) -> pd.DataFrame:
    data = pd.read_csv(file_path)

    required_columns = {
        TIME_COLUMN,
        TARGET_COLUMN,
        "training_row_ready",
        *feature_columns,
    }

    missing_columns = required_columns.difference(data.columns)

    if missing_columns:
        raise ValueError(
            f"Kolom training tidak lengkap: {sorted(missing_columns)}"
        )

    ready_mask = (
        data["training_row_ready"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    training_data = data.loc[ready_mask].copy()
    training_data[TIME_COLUMN] = pd.to_datetime(
        training_data[TIME_COLUMN],
        utc=True,
        errors="raise",
    )
    training_data["event_time_wib"] = (
        training_data[TIME_COLUMN]
        .dt.tz_convert(PROJECT_TIMEZONE)
    )
    training_data[TARGET_COLUMN] = (
        training_data[TARGET_COLUMN].astype(int)
    )

    training_data = (
        training_data
        .sort_values(TIME_COLUMN, kind="stable")
        .reset_index(drop=True)
    )

    if training_data[TIME_COLUMN].duplicated().any():
        raise ValueError("Dataset training memiliki timestamp duplikat.")

    if training_data[feature_columns].isna().any().any():
        raise ValueError("Fitur model masih memiliki nilai kosong.")

    if set(training_data[TARGET_COLUMN].unique()) != {0, 1}:
        raise ValueError("Target harus memiliki kelas 0 dan 1.")

    return training_data

def create_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    solver="lbfgs",
                    random_state=42,
                ),
            ),
        ]
    )

def annual_split(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = data.loc[
        data["event_time_wib"] < TRAIN_END
    ].copy()

    validation = data.loc[
        (data["event_time_wib"] >= TRAIN_END)
        & (data["event_time_wib"] < VALIDATION_END)
    ].copy()

    test = data.loc[
        data["event_time_wib"] >= VALIDATION_END
    ].copy()

    for name, split in (
        ("train", train),
        ("validation", validation),
        ("test", test),
    ):
        if split.empty:
            raise ValueError(f"Split {name} kosong.")

        if split[TARGET_COLUMN].nunique() != 2:
            raise ValueError(
                f"Split {name} tidak memiliki kedua kelas target."
            )

    if train[TIME_COLUMN].max() >= validation[TIME_COLUMN].min():
        raise ValueError(
            "Waktu train bertumpang tindih dengan validation."
        )

    if validation[TIME_COLUMN].max() >= test[TIME_COLUMN].min():
        raise ValueError(
            "Waktu validation bertumpang tindih dengan test."
        )

    return train, validation, test


def find_best_f1_threshold(
    labels: pd.Series,
    probabilities: np.ndarray,
) -> float:
    precision, recall, thresholds = precision_recall_curve(
        labels,
        probabilities,
    )

    denominator = precision[:-1] + recall[:-1]
    f1_values = np.divide(
        2 * precision[:-1] * recall[:-1],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )

    best_index = int(np.argmax(f1_values))
    return float(thresholds[best_index])


def evaluate_predictions(
    labels: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> dict:
    predictions = (probabilities >= threshold).astype(int)
    matrix = confusion_matrix(labels, predictions)

    return {
        "threshold": threshold,
        "accuracy": accuracy_score(labels, predictions),
        "precision": precision_score(
            labels,
            predictions,
            zero_division=0,
        ),
        "recall": recall_score(
            labels,
            predictions,
            zero_division=0,
        ),
        "f1": f1_score(
            labels,
            predictions,
            zero_division=0,
        ),
        "pr_auc": average_precision_score(
            labels,
            probabilities,
        ),
        "roc_auc": roc_auc_score(
            labels,
            probabilities,
        ),
        "confusion_matrix": matrix.tolist(),
    }


def split_metadata(split: pd.DataFrame) -> dict:
    return {
        "rows": len(split),
        "start_time_utc": split[TIME_COLUMN].min().isoformat(),
        "end_time_utc": split[TIME_COLUMN].max().isoformat(),
        "positive_rows": int(split[TARGET_COLUMN].sum()),
        "positive_rate": float(split[TARGET_COLUMN].mean()),
    }


def main() -> None:
    arguments = parse_arguments()
    feature_columns = get_model_feature_columns()
    processed_file = find_latest_processed_file(
        arguments.processed_dir
    )

    data = load_training_data(
        processed_file,
        feature_columns,
    )
    train, validation, test = annual_split(data)

    # Model seleksi hanya melihat tahun pertama.
    selection_model = create_model()
    selection_model.fit(
        train[feature_columns],
        train[TARGET_COLUMN],
    )

    validation_probabilities = selection_model.predict_proba(
        validation[feature_columns]
    )[:, 1]

    # Threshold hanya ditentukan menggunakan validation set.
    decision_threshold = find_best_f1_threshold(
        validation[TARGET_COLUMN],
        validation_probabilities,
    )

    validation_metrics = evaluate_predictions(
        validation[TARGET_COLUMN],
        validation_probabilities,
        decision_threshold,
    )

    # Setelah konfigurasi dipilih, model final dilatih menggunakan
    # train dan validation. Test tetap belum pernah dilihat.
    final_training_data = pd.concat(
        [train, validation],
        ignore_index=True,
    )

    final_model = create_model()
    final_model.fit(
        final_training_data[feature_columns],
        final_training_data[TARGET_COLUMN],
    )

    test_probabilities = final_model.predict_proba(
        test[feature_columns]
    )[:, 1]

    test_metrics = evaluate_predictions(
        test[TARGET_COLUMN],
        test_probabilities,
        decision_threshold,
    )

    trained_at = datetime.now(timezone.utc)
    run_id = trained_at.strftime("%Y%m%dT%H%M%SZ")
    run_directory = arguments.output_dir / run_id
    run_directory.mkdir(parents=True, exist_ok=False)

    model_path = run_directory / "model.joblib"
    metrics_path = run_directory / "metrics.json"
    metadata_path = run_directory / "metadata.json"

    model_bundle = {
        "model": final_model,
        "feature_columns": feature_columns,
        "decision_threshold": decision_threshold,
        "target_column": TARGET_COLUMN,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "rain_target_threshold_mm": RAIN_TARGET_THRESHOLD_MM,
    }

    joblib.dump(model_bundle, model_path)

    metrics = {
        "validation": validation_metrics,
        "test": test_metrics,
    }

    metadata = {
        "run_id": run_id,
        "trained_at_utc": trained_at.isoformat(),
        "model_type": "logistic_regression",
        "processed_file": str(processed_file),
        "processed_file_sha256": calculate_sha256(
            processed_file
        ),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_count": len(feature_columns),
        "feature_columns": feature_columns,
        "target_column": TARGET_COLUMN,
        "rain_target_threshold_mm": (
            RAIN_TARGET_THRESHOLD_MM
        ),
        "decision_threshold": decision_threshold,
        "split_strategy": "annual_holdout",
        "model_selection_training_period": (
            "2023-10-01 through 2024-09-30"
        ),
        "validation_period": (
            "2024-10-01 through 2025-09-30"
        ),
        "final_model_training_period": (
            "2023-10-01 through 2025-09-30"
        ),
        "test_period": (
            "2025-10-01 through 2026-09-30"
        ),
    }

    metrics_path.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("Baseline training selesai.")
    print(f"Processed file : {processed_file}")
    print(f"Jumlah fitur   : {len(feature_columns)}")
    print(f"Train rows     : {len(train)}")
    print(f"Validation rows: {len(validation)}")
    print(f"Test rows      : {len(test)}")
    print(f"Threshold      : {decision_threshold:.4f}")
    print()
    print("Validation metrics:")
    print(json.dumps(validation_metrics, indent=2))
    print()
    print("Test metrics:")
    print(json.dumps(test_metrics, indent=2))
    print()
    print(f"Model          : {model_path}")
    print(f"Metrics        : {metrics_path}")
    print(f"Metadata       : {metadata_path}")
    print(
        "Final train rows:"
        f" {len(final_training_data)}"
    )


if __name__ == "__main__":
    main()