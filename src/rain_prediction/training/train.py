from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from importlib.metadata import version

from lightgbm import LGBMClassifier
from xgboost import XGBClassifier

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data.preprocess import (
    FEATURE_SCHEMA_VERSION,
    RAIN_TARGET_THRESHOLD_MM,
    get_model_feature_columns,
)
from rain_prediction.training.train_baseline import (
    TARGET_COLUMN,
    TIME_COLUMN,
    annual_split,
    calculate_sha256,
    evaluate_predictions,
    find_best_f1_threshold,
    find_latest_processed_file,
    load_training_data,
    split_metadata,
)


MODEL_CHOICES = (
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
    "xgboost",
    "lightgbm",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Melatih beberapa kandidat model prediksi hujan "
            "dan mencatat eksperimen ke MLflow."
        )
    )

    parser.add_argument(
        "--model",
        choices=MODEL_CHOICES,
        required=True,
        help="Algoritma yang digunakan pada eksperimen.",
    )
    parser.add_argument(
        "--run-name",
        required=True,
        help="Nama run yang ditampilkan pada MLflow.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed/open_meteo_history"),
    )
    parser.add_argument(
        "--tracking-uri",
        default=os.getenv(
            "MLFLOW_TRACKING_URI",
            "http://127.0.0.1:5001",
        ),
    )
    parser.add_argument(
        "--experiment-name",
        default="rain-risk-hyperparameter-tuning",
    )
    parser.add_argument(
        "--class-weight",
        choices=("none", "balanced"),
        default="none",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
    )

    # Logistic Regression
    parser.add_argument(
        "--c",
        type=float,
        default=1.0,
        help="Inverse regularization strength Logistic Regression.",
    )
    parser.add_argument(
        "--logistic-max-iter",
        type=int,
        default=2000,
    )

    # Random Forest
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--min-samples-leaf",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--max-features",
        choices=("sqrt", "log2"),
        default="sqrt",
    )

    # HistGradientBoosting
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--boosting-max-iter",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--max-leaf-nodes",
        type=int,
        default=31,
    )
    parser.add_argument(
        "--boosting-min-samples-leaf",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--l2-regularization",
        type=float,
        default=1.0,
    )
        # Parameter bersama untuk XGBoost dan LightGBM
    parser.add_argument(
        "--subsample",
        type=float,
        default=0.9,
    )
    parser.add_argument(
        "--colsample-bytree",
        type=float,
        default=0.9,
    )
    parser.add_argument(
        "--reg-alpha",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--reg-lambda",
        type=float,
        default=1.0,
    )

    # XGBoost
    parser.add_argument(
        "--xgb-min-child-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--xgb-gamma",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--xgb-scale-pos-weight",
        type=float,
        default=1.0,
        help=(
            "Bobot kelas hujan pada XGBoost. "
            "Gunakan sekitar jumlah negatif/jumlah positif."
        ),
    )

    # LightGBM
    parser.add_argument(
        "--lightgbm-num-leaves",
        type=int,
        default=31,
    )
    parser.add_argument(
        "--lightgbm-min-child-samples",
        type=int,
        default=20,
    )

    arguments = parser.parse_args()
    validate_arguments(arguments)
    return arguments


def validate_arguments(
    arguments: argparse.Namespace,
) -> None:
    def require_positive(
        parameters: dict[str, int | float],
    ) -> None:
        invalid = [
            name
            for name, value in parameters.items()
            if value <= 0
        ]
        if invalid:
            raise ValueError(
                "Parameter harus lebih dari nol: "
                f"{invalid}"
            )

    def require_non_negative(
        parameters: dict[str, int | float],
    ) -> None:
        invalid = [
            name
            for name, value in parameters.items()
            if value < 0
        ]
        if invalid:
            raise ValueError(
                "Parameter tidak boleh negatif: "
                f"{invalid}"
            )

    def require_fraction(
        parameters: dict[str, float],
    ) -> None:
        invalid = [
            name
            for name, value in parameters.items()
            if not 0 < value <= 1
        ]
        if invalid:
            raise ValueError(
                "Parameter harus berada dalam "
                "rentang (0, 1]: "
                f"{invalid}"
            )

    if arguments.model == "logistic_regression":
        require_positive(
            {
                "c": arguments.c,
                "logistic_max_iter": (
                    arguments.logistic_max_iter
                ),
            }
        )
        return

    if arguments.model == "random_forest":
        require_positive(
            {
                "n_estimators": (
                    arguments.n_estimators
                ),
                "max_depth": arguments.max_depth,
                "min_samples_leaf": (
                    arguments.min_samples_leaf
                ),
            }
        )
        return

    if arguments.model == "hist_gradient_boosting":
        require_positive(
            {
                "learning_rate": (
                    arguments.learning_rate
                ),
                "boosting_max_iter": (
                    arguments.boosting_max_iter
                ),
                "max_leaf_nodes": (
                    arguments.max_leaf_nodes
                ),
                "boosting_min_samples_leaf": (
                    arguments.boosting_min_samples_leaf
                ),
            }
        )
        require_non_negative(
            {
                "l2_regularization": (
                    arguments.l2_regularization
                ),
            }
        )
        return

    if arguments.model == "xgboost":
        require_positive(
            {
                "n_estimators": (
                    arguments.n_estimators
                ),
                "max_depth": arguments.max_depth,
                "learning_rate": (
                    arguments.learning_rate
                ),
                "xgb_scale_pos_weight": (
                    arguments.xgb_scale_pos_weight
                ),
            }
        )
        require_non_negative(
            {
                "xgb_min_child_weight": (
                    arguments.xgb_min_child_weight
                ),
                "xgb_gamma": arguments.xgb_gamma,
                "reg_alpha": arguments.reg_alpha,
                "reg_lambda": arguments.reg_lambda,
            }
        )
        require_fraction(
            {
                "subsample": arguments.subsample,
                "colsample_bytree": (
                    arguments.colsample_bytree
                ),
            }
        )
        return

    if arguments.model == "lightgbm":
        require_positive(
            {
                "n_estimators": (
                    arguments.n_estimators
                ),
                "max_depth": arguments.max_depth,
                "learning_rate": (
                    arguments.learning_rate
                ),
                "lightgbm_num_leaves": (
                    arguments.lightgbm_num_leaves
                ),
                "lightgbm_min_child_samples": (
                    arguments.lightgbm_min_child_samples
                ),
            }
        )
        require_non_negative(
            {
                "reg_alpha": arguments.reg_alpha,
                "reg_lambda": arguments.reg_lambda,
            }
        )
        require_fraction(
            {
                "subsample": arguments.subsample,
                "colsample_bytree": (
                    arguments.colsample_bytree
                ),
            }
        )

        maximum_leaves = 2**arguments.max_depth
        if (
            arguments.lightgbm_num_leaves
            > maximum_leaves
        ):
            raise ValueError(
                "lightgbm_num_leaves tidak boleh "
                "lebih besar dari 2**max_depth "
                f"({maximum_leaves})."
            )
        return

    raise ValueError(
        f"Model tidak didukung: {arguments.model}"
    )


def resolve_class_weight(value: str) -> str | None:
    if value == "none":
        return None
    return value


def create_model(arguments: argparse.Namespace) -> Any:
    class_weight = resolve_class_weight(
        arguments.class_weight
    )

    if arguments.model == "logistic_regression":
        return Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        C=arguments.c,
                        class_weight=class_weight,
                        max_iter=arguments.logistic_max_iter,
                        solver="lbfgs",
                        random_state=arguments.random_state,
                    ),
                ),
            ]
        )

    if arguments.model == "random_forest":
        return RandomForestClassifier(
            n_estimators=arguments.n_estimators,
            max_depth=arguments.max_depth,
            min_samples_leaf=arguments.min_samples_leaf,
            max_features=arguments.max_features,
            class_weight=class_weight,
            random_state=arguments.random_state,
            n_jobs=-1,
        )

    if arguments.model == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=arguments.learning_rate,
            max_iter=arguments.boosting_max_iter,
            max_leaf_nodes=arguments.max_leaf_nodes,
            min_samples_leaf=(
                arguments.boosting_min_samples_leaf
            ),
            l2_regularization=arguments.l2_regularization,
            class_weight=class_weight,
            early_stopping=False,
            random_state=arguments.random_state,
        )
        
    if arguments.model == "xgboost":
        return XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            n_estimators=arguments.n_estimators,
            max_depth=arguments.max_depth,
            learning_rate=arguments.learning_rate,
            min_child_weight=(
                arguments.xgb_min_child_weight
            ),
            gamma=arguments.xgb_gamma,
            subsample=arguments.subsample,
            colsample_bytree=(
                arguments.colsample_bytree
            ),
            reg_alpha=arguments.reg_alpha,
            reg_lambda=arguments.reg_lambda,
            scale_pos_weight=(
                arguments.xgb_scale_pos_weight
            ),
            random_state=arguments.random_state,
            n_jobs=-1,
        )

    if arguments.model == "lightgbm":
        return LGBMClassifier(
            objective="binary",
            boosting_type="gbdt",
            n_estimators=arguments.n_estimators,
            max_depth=arguments.max_depth,
            num_leaves=arguments.lightgbm_num_leaves,
            learning_rate=arguments.learning_rate,
            min_child_samples=(
                arguments.lightgbm_min_child_samples
            ),
            subsample=arguments.subsample,
            subsample_freq=1,
            colsample_bytree=(
                arguments.colsample_bytree
            ),
            reg_alpha=arguments.reg_alpha,
            reg_lambda=arguments.reg_lambda,
            class_weight=class_weight,
            random_state=arguments.random_state,
            n_jobs=-1,
            importance_type="gain",
            verbosity=-1,
        )
        
    raise ValueError(
        f"Model tidak didukung: {arguments.model}"
    )


def get_model_parameters(
    arguments: argparse.Namespace,
) -> dict[str, str | int | float]:
    parameters: dict[str, str | int | float] = {
        "model_type": arguments.model,
        "class_weight": arguments.class_weight,
        "random_state": arguments.random_state,
    }

    if arguments.model == "logistic_regression":
        parameters.update(
            {
                "c": arguments.c,
                "solver": "lbfgs",
                "logistic_max_iter": (
                    arguments.logistic_max_iter
                ),
                "scaler": "standard_scaler",
            }
        )

    elif arguments.model == "random_forest":
        parameters.update(
            {
                "n_estimators": arguments.n_estimators,
                "max_depth": arguments.max_depth,
                "min_samples_leaf": (
                    arguments.min_samples_leaf
                ),
                "max_features": arguments.max_features,
            }
        )

    elif arguments.model == "hist_gradient_boosting":
        parameters.update(
            {
                "learning_rate": arguments.learning_rate,
                "boosting_max_iter": (
                    arguments.boosting_max_iter
                ),
                "max_leaf_nodes": (
                    arguments.max_leaf_nodes
                ),
                "boosting_min_samples_leaf": (
                    arguments.boosting_min_samples_leaf
                ),
                "l2_regularization": (
                    arguments.l2_regularization
                ),
                "early_stopping": "false",
            }
        )
        
    elif arguments.model == "xgboost":
        parameters.update(
            {
                "library": "xgboost",
                "library_version": version("xgboost"),
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "tree_method": "hist",
                "n_estimators": (
                    arguments.n_estimators
                ),
                "max_depth": arguments.max_depth,
                "learning_rate": (
                    arguments.learning_rate
                ),
                "min_child_weight": (
                    arguments.xgb_min_child_weight
                ),
                "gamma": arguments.xgb_gamma,
                "subsample": arguments.subsample,
                "colsample_bytree": (
                    arguments.colsample_bytree
                ),
                "reg_alpha": arguments.reg_alpha,
                "reg_lambda": arguments.reg_lambda,
                "scale_pos_weight": (
                    arguments.xgb_scale_pos_weight
                ),
            }
        )

    elif arguments.model == "lightgbm":
        parameters.update(
            {
                "library": "lightgbm",
                "library_version": version("lightgbm"),
                "objective": "binary",
                "boosting_type": "gbdt",
                "n_estimators": (
                    arguments.n_estimators
                ),
                "max_depth": arguments.max_depth,
                "num_leaves": (
                    arguments.lightgbm_num_leaves
                ),
                "learning_rate": (
                    arguments.learning_rate
                ),
                "min_child_samples": (
                    arguments.lightgbm_min_child_samples
                ),
                "subsample": arguments.subsample,
                "subsample_freq": 1,
                "colsample_bytree": (
                    arguments.colsample_bytree
                ),
                "reg_alpha": arguments.reg_alpha,
                "reg_lambda": arguments.reg_lambda,
            }
        )
    return parameters


def predict_positive_probability(
    model: Any,
    features: pd.DataFrame,
) -> Any:
    probabilities = model.predict_proba(features)
    classes = list(model.classes_)

    if 1 not in classes:
        raise ValueError(
            "Model tidak memiliki kelas positif bernilai 1."
        )

    positive_index = classes.index(1)
    return probabilities[:, positive_index]


def evaluate_model(
    labels: pd.Series,
    probabilities: Any,
    threshold: float,
) -> dict[str, Any]:
    metrics = evaluate_predictions(
        labels,
        probabilities,
        threshold,
    )
    metrics["brier_score"] = brier_score_loss(
        labels,
        probabilities,
    )
    metrics["log_loss"] = log_loss(
        labels,
        probabilities,
        labels=[0, 1],
    )
    return metrics


def log_metric_group(
    prefix: str,
    metrics: dict[str, Any],
) -> None:
    excluded = {
        "confusion_matrix",
        "threshold",
    }

    for name, value in metrics.items():
        if name in excluded:
            continue
        mlflow.log_metric(
            f"{prefix}_{name}",
            float(value),
        )


def make_json_safe(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            default=float,
        )
    )


def save_deployment_bundle(
    directory: Path,
    model: Any,
    feature_columns: list[str],
    decision_threshold: float,
    metrics: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)

    bundle = {
        "model": model,
        "feature_columns": feature_columns,
        "decision_threshold": decision_threshold,
        "target_column": TARGET_COLUMN,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "rain_target_threshold_mm": (
            RAIN_TARGET_THRESHOLD_MM
        ),
    }

    joblib.dump(
        bundle,
        directory / "model.joblib",
    )
    (directory / "metrics.json").write_text(
        json.dumps(
            make_json_safe(metrics),
            indent=2,
        ),
        encoding="utf-8",
    )
    (directory / "metadata.json").write_text(
        json.dumps(
            make_json_safe(metadata),
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    arguments = parse_arguments()

    mlflow.set_tracking_uri(arguments.tracking_uri)
    mlflow.set_experiment(arguments.experiment_name)

    feature_columns = get_model_feature_columns()
    processed_file = find_latest_processed_file(
        arguments.processed_dir
    )
    processed_sha256 = calculate_sha256(
        processed_file
    )

    data = load_training_data(
        processed_file,
        feature_columns,
    )
    train, validation, test = annual_split(data)

    model_parameters = get_model_parameters(
        arguments
    )

    with mlflow.start_run(
        run_name=arguments.run_name
    ) as active_run:
        started_at = time.perf_counter()
        trained_at = datetime.now(timezone.utc)

        mlflow.set_tags(
            {
                "project": "MLOps-Rain-Prediction",
                "task": "rain-next-3-hours",
                "model_family": arguments.model,
                "feature_schema_version": (
                    FEATURE_SCHEMA_VERSION
                ),
                "selection_metric": (
                    "validation_pr_auc"
                ),
                "model_status": "candidate",
            }
        )

        mlflow.log_params(model_parameters)
        mlflow.log_params(
            {
                "processed_file": processed_file.name,
                "processed_file_sha256": (
                    processed_sha256
                ),
                "feature_count": len(feature_columns),
                "target_column": TARGET_COLUMN,
                "rain_target_threshold_mm": (
                    RAIN_TARGET_THRESHOLD_MM
                ),
                "split_strategy": "annual_holdout",
                "train_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                "final_training_rows": (
                    len(train) + len(validation)
                ),
            }
        )

        # Model untuk memilih konfigurasi dan threshold.
        # Model ini hanya dilatih menggunakan train split.
        selection_model = create_model(arguments)
        selection_model.fit(
            train[feature_columns],
            train[TARGET_COLUMN],
        )

        validation_probabilities = (
            predict_positive_probability(
                selection_model,
                validation[feature_columns],
            )
        )
        decision_threshold = (
            find_best_f1_threshold(
                validation[TARGET_COLUMN],
                validation_probabilities,
            )
        )
        validation_metrics = evaluate_model(
            validation[TARGET_COLUMN],
            validation_probabilities,
            decision_threshold,
        )

        # Setelah parameter dan threshold dipilih, model final
        # dilatih ulang menggunakan train + validation.
        final_training_data = pd.concat(
            [train, validation],
            ignore_index=True,
        )

        final_model = create_model(arguments)
        final_model.fit(
            final_training_data[feature_columns],
            final_training_data[TARGET_COLUMN],
        )

        test_probabilities = (
            predict_positive_probability(
                final_model,
                test[feature_columns],
            )
        )
        test_metrics = evaluate_model(
            test[TARGET_COLUMN],
            test_probabilities,
            decision_threshold,
        )

        duration_seconds = (
            time.perf_counter() - started_at
        )

        mlflow.log_metric(
            "decision_threshold",
            decision_threshold,
        )
        mlflow.log_metric(
            "training_duration_seconds",
            duration_seconds,
        )
        log_metric_group(
            "validation",
            validation_metrics,
        )
        log_metric_group(
            "test",
            test_metrics,
        )

        evaluation = {
            "validation": validation_metrics,
            "test": test_metrics,
        }
        mlflow.log_dict(
            make_json_safe(evaluation),
            "evaluation/metrics.json",
        )
        mlflow.log_dict(
            {
                "validation": (
                    validation_metrics[
                        "confusion_matrix"
                    ]
                ),
                "test": (
                    test_metrics[
                        "confusion_matrix"
                    ]
                ),
            },
            "evaluation/confusion_matrices.json",
        )
        mlflow.log_dict(
            {
                "feature_schema_version": (
                    FEATURE_SCHEMA_VERSION
                ),
                "feature_count": len(feature_columns),
                "feature_columns": feature_columns,
            },
            "metadata/features.json",
        )

        dvc_pointer = Path(
            "data/raw/open_meteo_history.dvc"
        )
        if dvc_pointer.is_file():
            mlflow.log_artifact(
                str(dvc_pointer),
                artifact_path="data_version",
            )

        input_example = (
            test[feature_columns]
            .head(5)
            .astype("float64")
            .copy()
        )
        predicted_example = final_model.predict(
            input_example
        )
        signature = infer_signature(
            input_example,
            predicted_example,
        )

        model_metadata = {
            "model_type": arguments.model,
            "decision_threshold": (
                decision_threshold
            ),
            "feature_schema_version": (
                FEATURE_SCHEMA_VERSION
            ),
            "dataset_sha256": processed_sha256,
            "selection_metric": (
                "validation_pr_auc"
            ),
        }

        mlflow.sklearn.log_model(
            sk_model=final_model,
            name="model",
            signature=signature,
            input_example=input_example,
            metadata=model_metadata,
            serialization_format="cloudpickle",
        )

        metadata = {
            "run_id": active_run.info.run_id,
            "run_name": arguments.run_name,
            "trained_at_utc": trained_at.isoformat(),
            "model_type": arguments.model,
            "model_parameters": model_parameters,
            "processed_file": str(processed_file),
            "processed_file_sha256": (
                processed_sha256
            ),
            "feature_schema_version": (
                FEATURE_SCHEMA_VERSION
            ),
            "feature_count": len(feature_columns),
            "feature_columns": feature_columns,
            "target_column": TARGET_COLUMN,
            "rain_target_threshold_mm": (
                RAIN_TARGET_THRESHOLD_MM
            ),
            "decision_threshold": (
                decision_threshold
            ),
            "selection_metric": (
                "validation_pr_auc"
            ),
            "split_strategy": "annual_holdout",
            "train": split_metadata(train),
            "validation": split_metadata(
                validation
            ),
            "test": split_metadata(test),
            "latest_validation_date": (
                test[TIME_COLUMN]
                .max()
                .isoformat()
            ),
            "training_duration_seconds": (
                duration_seconds
            ),
        }

        mlflow.log_dict(
            make_json_safe(metadata),
            "metadata/model_metadata.json",
        )

        # Bundle ini kompatibel dengan RainModelPredictor
        # yang sudah digunakan oleh backend proyek.
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_directory = (
                Path(temp_dir)
                / "deployment_bundle"
            )
            save_deployment_bundle(
                directory=bundle_directory,
                model=final_model,
                feature_columns=feature_columns,
                decision_threshold=(
                    decision_threshold
                ),
                metrics=evaluation,
                metadata=metadata,
            )
            mlflow.log_artifacts(
                str(bundle_directory),
                artifact_path="deployment_bundle",
            )

        print("Eksperimen MLflow selesai.")
        print(
            f"Run ID             : "
            f"{active_run.info.run_id}"
        )
        print(
            f"Run name           : "
            f"{arguments.run_name}"
        )
        print(
            f"Model              : "
            f"{arguments.model}"
        )
        print(
            f"Processed file     : "
            f"{processed_file}"
        )
        print(
            f"Jumlah fitur       : "
            f"{len(feature_columns)}"
        )
        print(
            f"Train rows         : "
            f"{len(train)}"
        )
        print(
            f"Validation rows    : "
            f"{len(validation)}"
        )
        print(
            f"Test rows          : "
            f"{len(test)}"
        )
        print(
            f"Decision threshold : "
            f"{decision_threshold:.4f}"
        )
        print()
        print("Validation metrics:")
        print(
            json.dumps(
                make_json_safe(
                    validation_metrics
                ),
                indent=2,
            )
        )
        print()
        print("Test metrics:")
        print(
            json.dumps(
                make_json_safe(
                    test_metrics
                ),
                indent=2,
            )
        )
        print()
        print(
            f"MLflow tracking URI: "
            f"{arguments.tracking_uri}"
        )
        print(
            f"Experiment         : "
            f"{arguments.experiment_name}"
        )


if __name__ == "__main__":
    main()