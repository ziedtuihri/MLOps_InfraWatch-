import pytest
from pydantic import ValidationError

from app import PredictionRequest, health


def test_health_returns_ok_status():
    assert health() == {"status": "ok"}


def test_prediction_request_accepts_non_negative_features():
    request = PredictionRequest(
        usage_counter=0,
        fs_excl_counter=1,
        task_size=2,
        end_data=3,
        policy=4,
        nivcsw=5,
    )

    assert request.usage_counter == 0


@pytest.mark.parametrize(
    "field",
    [
        "usage_counter",
        "fs_excl_counter",
        "task_size",
        "end_data",
        "policy",
        "nivcsw",
    ],
)
def test_prediction_request_rejects_negative_features(field):
    features = {
        "usage_counter": 0,
        "fs_excl_counter": 1,
        "task_size": 2,
        "end_data": 3,
        "policy": 4,
        "nivcsw": 5,
    }
    features[field] = -1

    with pytest.raises(ValidationError):
        PredictionRequest(**features)
