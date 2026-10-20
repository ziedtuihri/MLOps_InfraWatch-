#!/usr/bin/env python3

import argparse
import os

import joblib
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient


def load_model_artifact(model_path):
    """Load a model bundle from disk. Supports both a raw model and a dict bundle."""
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    bundle = joblib.load(model_path)
    if isinstance(bundle, dict):
        model = bundle.get("model")
        scaler = bundle.get("scaler")
    else:
        model = bundle
        scaler = None

    if model is None:
        raise ValueError("No model object was found in the file.")
    return model, scaler


def register_to_registry(model, experiment_name, registered_model_name, scaler=None):
    """Log a trained model to MLflow and register it in the model registry."""
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="Register_Model") as run:
        model_uri = f"runs:/{run.info.run_id}/model"
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            serialization_format="pickle",
        )
        model_version = mlflow.register_model(
            model_uri=model_uri, name=registered_model_name
        )

        client = MlflowClient()
        client.update_registered_model(
            name=registered_model_name,
            description="Malware detection model trained on process telemetry features.",
        )
        client.set_registered_model_tag(
            registered_model_name, "project", "MalwareDetection"
        )
        client.set_registered_model_tag(
            registered_model_name, "author", "MLOps_InfraWatch"
        )
        client.set_registered_model_tag(
            registered_model_name, "algorithm", "RandomForestClassifier"
        )
        client.set_registered_model_tag(
            registered_model_name, "framework", "scikit-learn"
        )
        client.set_registered_model_tag(
            registered_model_name, "mlflow-version", mlflow.__version__
        )

        client.update_model_version(
            name=registered_model_name,
            version=model_version.version,
            description="Registered from the malware detection pipeline.",
        )
        client.set_model_version_tag(
            registered_model_name, model_version.version, "stage", "Staging"
        )
        client.set_model_version_tag(
            registered_model_name, model_version.version, "source", model_uri
        )
        client.set_model_version_tag(
            registered_model_name, model_version.version, "framework", "scikit-learn"
        )
        client.set_model_version_tag(
            registered_model_name,
            model_version.version,
            "scaler_included",
            str(scaler is not None),
        )
        client.set_model_version_tag(
            registered_model_name, model_version.version, "author", "MLOps_InfraWatch"
        )

        return model_version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register a model bundle in MLflow Model Registry."
    )
    parser.add_argument(
        "--model-path",
        type=str,
        required=True,
        help="Path to a model bundle (.pkl or .joblib).",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="Malware_Detection_Experiment",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--registered-model-name",
        type=str,
        default="malware-detection-model",
        help="Model name in the registry.",
    )
    args = parser.parse_args()

    try:
        model, scaler = load_model_artifact(args.model_path)
        register_to_registry(
            model, args.experiment_name, args.registered_model_name, scaler=scaler
        )
        print("Model registered successfully.")
    except Exception as exc:  # pragma: no cover - CLI error reporting
        print(f"An error occurred: {exc}")
        raise
