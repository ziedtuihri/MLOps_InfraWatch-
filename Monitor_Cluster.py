"""Train and compare models for datacenter cluster outage prediction."""

from pathlib import Path

import matplotlib.pyplot as plt
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
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier


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


def main():
    project_root = Path(__file__).resolve().parent.parent
    dataset_path = project_root / "dataset" / "datacenter_warehouse_50k.csv"
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Datacenter telemetry dataset not found: {dataset_path}. "
            "Place datacenter_warehouse_50k.csv in the repository dataset/ folder."
        )

    telemetry = pd.read_csv(dataset_path)
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
    for name, classifier in models.items():
        train_features, test_features = (
            (X_train_scaled, X_test_scaled)
            if name in scaled_models
            else (X_train, X_test)
        )
        classifier.fit(train_features, y_train)
        model_predictions = classifier.predict(test_features)
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


if __name__ == "__main__":
    main()
