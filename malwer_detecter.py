"""Feature extraction, training, and scanning utilities for malware detection."""

import logging
import math
import os
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [
    "usage_counter",
    "fs_excl_counter",
    "task_size",
    "end_data",
    "policy",
    "nivcsw",
]

logger = logging.getLogger("malwer_detecter")


def calculate_entropy(file_path):
    """Calculate Shannon entropy for a file."""
    with open(file_path, "rb") as handle:
        byte_array = handle.read()
    if not byte_array:
        return 0.0

    counts = [0] * 256
    for byte in byte_array:
        counts[byte] += 1

    file_size = len(byte_array)
    entropy = 0.0
    for count in counts:
        if count == 0:
            continue
        probability = count / file_size
        entropy -= probability * math.log2(probability)
    return entropy


def get_hashes(file_path):
    """Generate MD5 and SHA256 hashes for a file."""
    import hashlib

    with open(file_path, "rb") as handle:
        file_bytes = handle.read()
    return hashlib.md5(file_bytes).hexdigest(), hashlib.sha256(file_bytes).hexdigest()


def extract_file_features(file_path):
    """Extract the six values used by the malware model from a file."""
    try:
        size = os.path.getsize(file_path)
        entropy = calculate_entropy(file_path)
        _, extension = os.path.splitext(file_path)
        is_executable = 1 if extension.lower() == ".exe" else 0
        last_accessed = os.path.getatime(file_path)
        last_modified = os.path.getmtime(file_path)
        created = os.path.getctime(file_path)

        return {
            "usage_counter": float(size),
            "fs_excl_counter": float(entropy),
            "task_size": float(is_executable),
            "end_data": float(last_accessed),
            "policy": float(last_modified),
            "nivcsw": float(created),
        }
    except OSError:
        return None


def load_dataset(path):
    """Load and clean the malware dataset."""
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    df = pd.read_csv(dataset_path)
    required_columns = FEATURE_COLUMNS + ["classification"]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    cleaned = df.loc[:, required_columns].copy()
    for column in FEATURE_COLUMNS:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    cleaned["classification"] = (
        cleaned["classification"].astype(str).str.strip().str.lower()
    )
    cleaned = cleaned.dropna(subset=FEATURE_COLUMNS + ["classification"]).reset_index(
        drop=True
    )
    return cleaned


def train_malware_model(df):
    """Train a Random Forest model on the malware dataset and return the model, scaler, and metrics."""
    X = df[FEATURE_COLUMNS]
    y = df["classification"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.3,
        random_state=42,
        stratify=y,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        max_depth=None,
        min_samples_leaf=1,
        class_weight="balanced",
    )
    model.fit(X_train_scaled, y_train)

    predictions = model.predict(X_test_scaled)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, predictions)), 6),
        "precision": round(
            float(
                precision_score(
                    y_test, predictions, pos_label="malware", zero_division=0
                )
            ),
            6,
        ),
        "recall": round(
            float(
                recall_score(y_test, predictions, pos_label="malware", zero_division=0)
            ),
            6,
        ),
        "f1": round(
            float(f1_score(y_test, predictions, pos_label="malware", zero_division=0)),
            6,
        ),
    }
    return model, scaler, metrics


def scan_directory(directory_path, model, scaler, feature_columns=None):
    """Scan a directory tree and label each file as malware or benign."""
    if feature_columns is None:
        feature_columns = FEATURE_COLUMNS

    results = []
    sample_id = 0
    for root, _, files in os.walk(directory_path):
        for file_name in sorted(files):
            file_path = os.path.join(root, file_name)
            sample_id += 1
            encoded_file_name = quote(file_name, safe="._-")
            feature_map = extract_file_features(file_path)
            if feature_map is None:
                logger.info(
                    "event=scan_error sample_id=%d file_name=%s "
                    "details=unable_to_read_file",
                    sample_id,
                    encoded_file_name,
                )
                results.append(
                    {
                        "file": file_path,
                        "prediction": "error",
                        "details": "unable to read file",
                    }
                )
                continue
            feature_vector = [float(feature_map[column]) for column in feature_columns]
            feature_frame = pd.DataFrame([feature_vector], columns=feature_columns)
            scaled = scaler.transform(feature_frame)
            prediction = model.predict(scaled)[0]
            result = {"file": file_path, "prediction": str(prediction).lower()}
            feature_values = " ".join(
                f"feature_{column}={feature_map[column]:.6f}"
                for column in feature_columns
            )
            logger.info(
                "event=prediction_completed sample_id=%d file_name=%s "
                "prediction=%s %s",
                sample_id,
                encoded_file_name,
                result["prediction"],
                feature_values,
            )
            print(f"{result['prediction']}: {file_path}")
            results.append(result)
    return results
