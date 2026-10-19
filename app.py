import os

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from malwer_detecter import FEATURE_COLUMNS
from main import DEFAULT_DATASET, logger, train_model

MODEL_PATH = os.getenv("MODEL_PATH", "/models/malware_detection_model.pkl")

app = FastAPI(title="MLOps InfraWatch API", version="1.0.0")


class PredictionRequest(BaseModel):
    usage_counter: float = Field(ge=0, allow_inf_nan=False)
    fs_excl_counter: float = Field(ge=0, allow_inf_nan=False)
    task_size: float = Field(ge=0, allow_inf_nan=False)
    end_data: float = Field(ge=0, allow_inf_nan=False)
    policy: float = Field(ge=0, allow_inf_nan=False)
    nivcsw: float = Field(ge=0, allow_inf_nan=False)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/train")
def train():
    model, _, metrics = train_model(
        dataset_path=str(DEFAULT_DATASET),
        model_path=MODEL_PATH,
    )
    return {
        "status": "trained",
        "model": type(model).__name__,
        "metrics": metrics,
    }


@app.post("/predict")
def predict(request: PredictionRequest):
    try:
        bundle = joblib.load(MODEL_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="No trained model is available. Call POST /train first.",
        ) from exc

    features = request.dict()
    feature_frame = pd.DataFrame([features], columns=FEATURE_COLUMNS)
    scaled_features = bundle["scaler"].transform(feature_frame)
    prediction = str(bundle["model"].predict(scaled_features)[0]).lower()

    logger.info(
        "event=prediction_completed prediction=%s feature_usage_counter=%s "
        "feature_fs_excl_counter=%s feature_task_size=%s feature_end_data=%s "
        "feature_policy=%s feature_nivcsw=%s",
        prediction,
        features["usage_counter"],
        features["fs_excl_counter"],
        features["task_size"],
        features["end_data"],
        features["policy"],
        features["nivcsw"],
    )
    return {"prediction": prediction}
