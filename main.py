import argparse
import logging
import math
import os
from pathlib import Path
from urllib.parse import quote

import joblib
import pandas as pd

from malwer_detecter import (
    FEATURE_COLUMNS,
    extract_file_features,
    load_dataset,
    scan_directory,
    train_malware_model,
)
from logging_config import setup_logging

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "logs" / "malwer_detecter.log"
logger = setup_logging(
    os.getenv("APP_LOG_FILE", str(DEFAULT_LOG_PATH)), level=logging.INFO
)

DEFAULT_DATASET = Path("dataset") / "malwareDataset.csv"
DEFAULT_MODEL_PATH = Path("malware_detection_model.pkl")


def train_model(
    dataset_path: str = str(DEFAULT_DATASET), model_path: str = str(DEFAULT_MODEL_PATH)
):
    """Train and persist the malware detection model."""
    logger.info("Loading malware dataset from %s", dataset_path)
    df = load_dataset(dataset_path)
    logger.info("Dataset loaded with %s rows and %s columns", df.shape[0], df.shape[1])

    model, scaler, metrics = train_malware_model(df)

    bundle = {
        "model": model,
        "scaler": scaler,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
    }
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    logger.info("Saved model bundle to %s", model_path)
    logger.info("Validation metrics: %s", metrics)
    dataset_name = quote(Path(dataset_path).name, safe="._-")
    test_rows = math.ceil(df.shape[0] * 0.3)
    logger.info(
        "event=training_completed dataset=%s target=classification "
        "positive_class=malware dataset_rows=%d dataset_columns=%d "
        "feature_count=%d feature_columns=%s train_rows=%d test_rows=%d "
        "model=%s metric_accuracy=%.6f metric_precision=%.6f "
        "metric_recall=%.6f metric_f1=%.6f",
        dataset_name,
        df.shape[0],
        df.shape[1],
        len(FEATURE_COLUMNS),
        ",".join(FEATURE_COLUMNS),
        df.shape[0] - test_rows,
        test_rows,
        type(model).__name__,
        metrics["accuracy"],
        metrics["precision"],
        metrics["recall"],
        metrics["f1"],
    )
    return model, scaler, metrics


def predict_directory(directory_path: str, model_path: str = str(DEFAULT_MODEL_PATH)):
    """Scan a directory for malware using the saved model."""
    bundle = joblib.load(model_path)
    model = bundle["model"]
    scaler = bundle["scaler"]
    feature_columns = bundle.get("feature_columns", FEATURE_COLUMNS)

    logger.info("Scanning %s with model %s", directory_path, model_path)
    results = scan_directory(
        directory_path, model=model, scaler=scaler, feature_columns=feature_columns
    )
    return results


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train and run malware detection on the provided dataset."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(DEFAULT_DATASET),
        help="Path to the CSV dataset.",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=str(DEFAULT_MODEL_PATH),
        help="Path where the trained model bundle will be stored.",
    )
    parser.add_argument(
        "--scan-dir",
        type=str,
        default=None,
        help="Directory to scan for malware after training or loading the model.",
    )
    parser.add_argument(
        "--no-train",
        action="store_true",
        help="Skip training and use the existing model bundle if present.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.scan_dir:
        predict_directory(args.scan_dir, model_path=args.model_path)
        return

    if not args.no_train:
        train_model(dataset_path=args.dataset, model_path=args.model_path)
        return

    if not Path(args.model_path).exists():
        raise FileNotFoundError(f"Model bundle not found: {args.model_path}")

    logger.info("Using existing model bundle at %s", args.model_path)
    bundle = joblib.load(args.model_path)
    logger.info("Loaded model with metrics: %s", bundle.get("metrics"))


if __name__ == "__main__":
    main()
