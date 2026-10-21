"""Log holdout regression metrics for an ElasticNet Iris model."""

import logging
import os
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.datasets import load_iris
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from logging_config import setup_logging

MLFLOW_EXPERIMENT = "ElasticNet Iris Regression"
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "elasticnet_iris.log"
logger = logging.getLogger("elasticnet_iris")


def compute_metrics(actual, predicted):
    """Calculate holdout RMSE and R²."""
    return {
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "r2": float(r2_score(actual, predicted)),
    }


def main():
    log_path = os.getenv("IRIS_LOG_FILE", str(DEFAULT_LOG_PATH))
    setup_logging(log_path)

    iris = load_iris()
    iris_df = pd.DataFrame(data=iris.data, columns=iris.feature_names)
    iris_df["quality"] = (iris.target == 2).astype(int)
    train_df, test_df = train_test_split(
        iris_df,
        test_size=0.2,
        random_state=42,
    )

    train_dataset = mlflow.data.from_pandas(train_df, name="iris_train")
    test_dataset = mlflow.data.from_pandas(test_df, name="iris_test")
    train_x = train_dataset.df.drop(columns=["quality"])
    train_y = train_dataset.df["quality"]
    test_x = test_dataset.df.drop(columns=["quality"])
    test_y = test_dataset.df["quality"]

    model = ElasticNet(alpha=0.5, l1_ratio=0.5, random_state=42)
    model.fit(train_x, train_y)

    mlflow.set_experiment(experiment_name=MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name="elasticnet_iris_training"):
        mlflow.log_params({"alpha": 0.5, "l1_ratio": 0.5})
        mlflow.log_input(train_dataset, context="training")
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            name="elasticnet",
            params={"alpha": 0.5, "l1_ratio": 0.5},
            input_example=train_x.head(),
        )

        logged_model = mlflow.get_logged_model(model_info.model_id)
        metrics = compute_metrics(test_y, model.predict(test_x))
        mlflow.log_metrics(
            metrics=metrics,
            model_id=logged_model.model_id,
            dataset=test_dataset,
        )
        logged_model = mlflow.get_logged_model(model_info.model_id)

    logger.info(
        "event=elasticnet_evaluation_completed dataset=iris model=ElasticNet "
        "test_rows=%d metric_rmse=%.6f metric_r2=%.6f",
        len(test_y),
        metrics["rmse"],
        metrics["r2"],
    )
    print(f"{logged_model.model_id} {logged_model.metrics}")


if __name__ == "__main__":
    main()
