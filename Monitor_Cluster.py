"""Train and compare models for datacenter cluster outage prediction."""

import logging
import os
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

from logging_config import setup_logging
from mlflow_utils import mlflow_run


logger = logging.getLogger("cluster_monitoring")
MLFLOW_EXPERIMENT = "Datacenter Outage Prediction"


REQUIRED_COLUMNS = [
    "Server_Age_Years",
    "Workload_Intensity",
    "CPU_Usage_Pct",
    "Memory_Usage_Pct",
    "Storage_Utilization_Pct",
    "Active_IOPS",
    "Power_Consumption_kW",
    "Carbon_Emission_kg",
    "Network_Throughput_Gbps",
    "Packet_Rate",
    "Failed_Logins",
]


def _log_model_run(
    name,
    model,
    result,
    predictions,
    y_test,
    input_example,
    training_data,
):
    """Log one evaluated outage model and its reproducibility artifacts."""
    classes = [0, 1]
    report = classification_report(
        y_test, predictions, labels=classes, output_dict=True, zero_division=0
    )
    matrix = confusion_matrix(y_test, predictions, labels=classes)
    model_params = {
        key: value
        for key, value in model.get_params(deep=True).items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }

    with mlflow_run(MLFLOW_EXPERIMENT, f"{name.lower().replace(' ', '_')}_training"):
        mlflow.log_params(
            {
                "model": name,
                "target": "Is_Outage",
                "positive_class": "outage",
                "test_size": 0.3,
                "random_state": 42,
                "train_rows": len(training_data),
                "test_rows": len(input_example),
                "feature_count": len(REQUIRED_COLUMNS),
                **model_params,
            }
        )
        mlflow.log_metrics(
            {
                "accuracy": float(result["accuracy"]),
                "outage_precision": float(result["outage_precision"]),
                "outage_recall": float(result["outage_recall"]),
                "outage_f1": float(result["outage_f1"]),
            }
        )
        mlflow.log_input(
            mlflow.data.from_pandas(
                training_data, source="datacenter_warehouse_50k.csv"
            ),
            context="training",
        )
        mlflow.log_text(
            "\n".join(REQUIRED_COLUMNS), artifact_file="feature_columns.txt"
        )
        mlflow.log_dict(
            report, artifact_file="evaluation/classification_report.json"
        )
        mlflow.log_dict(
            {"labels": classes, "matrix": matrix.tolist()},
            artifact_file="evaluation/confusion_matrix.json",
        )
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            input_example=input_example.head(min(5, len(input_example))),
            serialization_format="pickle",
        )


def main():
    project_root = Path(__file__).resolve().parent
    log_path = os.getenv(
        "CLUSTER_LOG_FILE", str(project_root / "logs" / "cluster_monitoring.log")
    )
    setup_logging(log_path)
    dataset_path = project_root / "dataset" / "datacenter_warehouse_50k.csv"
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Datacenter telemetry dataset not found: {dataset_path}. "
            "Place datacenter_warehouse_50k.csv in the repository dataset/ folder."
        )

    telemetry = pd.read_csv(dataset_path)
    dataset_columns = telemetry.shape[1]
    print(f"Loaded {len(telemetry):,} rows from {dataset_path}")
    print(telemetry.head())

    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(telemetry.columns))
    if missing_columns:
        raise ValueError(
            f"Dataset is missing required telemetry columns: {missing_columns}"
        )

    telemetry[REQUIRED_COLUMNS] = telemetry[REQUIRED_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    )
    missing_values = telemetry[REQUIRED_COLUMNS].isna().sum()
    print("Missing values in model columns before cleaning:")
    print(missing_values[missing_values > 0].sort_values(ascending=False))
    telemetry = telemetry.dropna(subset=REQUIRED_COLUMNS).copy()
    print(f"Rows available after cleaning: {len(telemetry):,}")

    base_condition = (
        (telemetry["CPU_Usage_Pct"] > 80) & (telemetry["Memory_Usage_Pct"] > 75)
    )
    noise = np.random.default_rng(42).random(len(telemetry)) < 0.035
    telemetry["Is_Outage"] = (base_condition.to_numpy() ^ noise).astype(int)

    features = telemetry[REQUIRED_COLUMNS]
    target = telemetry["Is_Outage"]
    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.3, random_state=42, stratify=target
    )
    print(f"Outage class counts:\n{target.value_counts().sort_index()}")
    print(f"Training rows: {len(X_train):,}; test rows: {len(X_test):,}")
    training_data = X_train.copy()
    training_data["Is_Outage"] = y_train

    model = RandomForestClassifier(
        n_estimators=100, random_state=42, class_weight="balanced", n_jobs=-1
    )
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    rf_metrics = {
        "accuracy": accuracy_score(y_test, predictions),
        "outage_precision": precision_score(
            y_test, predictions, pos_label=1, zero_division=0
        ),
        "outage_recall": recall_score(
            y_test, predictions, pos_label=1, zero_division=0
        ),
        "outage_f1": f1_score(y_test, predictions, pos_label=1, zero_division=0),
    }
    _log_model_run(
        "Random Forest",
        model,
        rf_metrics,
        predictions,
        y_test,
        X_test,
        training_data,
    )
    print("Random Forest holdout metrics:")
    print(pd.Series(rf_metrics, name="score"))
    print(classification_report(y_test, predictions, zero_division=0))

    sns.heatmap(
        confusion_matrix(y_test, predictions), annot=True, fmt="d", cmap="Blues"
    )
    plt.xlabel("Predicted outage")
    plt.ylabel("Actual outage")
    plt.title("Random Forest holdout confusion matrix")
    plt.tight_layout()
    plt.show()

    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]
    importance_df = pd.DataFrame(
        {
            "feature": np.array(REQUIRED_COLUMNS)[indices],
            "importance": importances[indices],
        }
    )
    sns.barplot(
        data=importance_df, x="importance", y="feature", color="steelblue"
    )
    plt.title("Random Forest feature importance for outage prediction")
    plt.tight_layout()
    plt.show()
    for rank, row in enumerate(importance_df.itertuples(index=False), start=1):
        logger.info(
            "event=feature_importance_completed "
            "dataset=datacenter_warehouse_50k.csv model=Random_Forest "
            "feature_column=%s feature_importance=%.6f importance_rank=%d",
            row.feature,
            row.importance,
            rank,
        )

    numeric_columns = telemetry.select_dtypes(
        include=["float64", "int64", "int32"]
    ).columns
    correlation_matrix = telemetry[numeric_columns].corr()
    plt.figure(figsize=(12, 10))
    sns.heatmap(
        correlation_matrix,
        annot=True,
        cmap="coolwarm",
        fmt=".2f",
        linewidths=0.5,
    )
    plt.title("Pearson Correlation Heatmap of Datacenter Telemetry Metrics")
    plt.tight_layout()
    plt.show()

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    models = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, random_state=42, class_weight="balanced"
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100, random_state=42
        ),
        "Decision Tree": DecisionTreeClassifier(
            max_depth=5, random_state=42, class_weight="balanced"
        ),
        "Linear SVM": LinearSVC(
            max_iter=2000, random_state=42, class_weight="balanced", dual=False
        ),
        "K-Nearest Neighbors": KNeighborsClassifier(n_neighbors=5),
    }
    scaled_models = {
        "Logistic Regression",
        "Linear SVM",
        "K-Nearest Neighbors",
    }
    comparison_results = [{"model": "Random Forest", **rf_metrics}]
    evaluation_predictions = {"Random Forest": predictions}
    evaluation_models = {"Random Forest": model}
    for name, classifier in models.items():
        train_features, test_features = (
            (X_train_scaled, X_test_scaled)
            if name in scaled_models
            else (X_train, X_test)
        )
        classifier.fit(train_features, y_train)
        model_predictions = classifier.predict(test_features)
        evaluation_models[name] = (
            make_pipeline(scaler, classifier) if name in scaled_models else classifier
        )
        evaluation_predictions[name] = model_predictions
        comparison_results.append(
            {
                "model": name,
                "accuracy": accuracy_score(y_test, model_predictions),
                "outage_precision": precision_score(
                    y_test, model_predictions, pos_label=1, zero_division=0
                ),
                "outage_recall": recall_score(
                    y_test, model_predictions, pos_label=1, zero_division=0
                ),
                "outage_f1": f1_score(
                    y_test, model_predictions, pos_label=1, zero_division=0
                ),
            }
        )

    comparison_df = pd.DataFrame(comparison_results).set_index("model")
    print("Model comparison, sorted by outage F1:")
    print(comparison_df.sort_values("outage_f1", ascending=False))

    for result in comparison_results[1:]:
        name = result["model"]
        _log_model_run(
            name,
            evaluation_models[name],
            result,
            evaluation_predictions[name],
            y_test,
            X_test,
            training_data,
        )

    feature_columns = ",".join(REQUIRED_COLUMNS)
    for result in comparison_results:
        matrix = confusion_matrix(
            y_test, evaluation_predictions[result["model"]], labels=[0, 1]
        )
        logger.info(
            "event=model_evaluation_completed dataset=datacenter_warehouse_50k.csv "
            "target=Is_Outage positive_class=outage model=%s "
            "dataset_rows=%d dataset_columns=%d feature_count=%d "
            "feature_columns=%s train_rows=%d test_rows=%d "
            "metric_accuracy=%.6f metric_precision=%.6f metric_recall=%.6f "
            "metric_f1=%.6f true_negative=%d false_positive=%d "
            "false_negative=%d true_positive=%d",
            result["model"].replace(" ", "_"),
            len(telemetry),
            dataset_columns,
            len(REQUIRED_COLUMNS),
            feature_columns,
            len(X_train),
            len(X_test),
            result["accuracy"],
            result["outage_precision"],
            result["outage_recall"],
            result["outage_f1"],
            matrix[0, 0],
            matrix[0, 1],
            matrix[1, 0],
            matrix[1, 1],
        )


if __name__ == "__main__":
    main()
