# Malware Detection Pipeline

This project trains a malware detector from the dataset stored in `dataset/malwareDataset.csv` and exposes a CLI workflow for both training and scanning.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Train the model

```bash
python main.py --dataset dataset/malwareDataset.csv --model-path malware_detection_model.pkl
```

## Scan a directory

```bash
python main.py --scan-dir /path/to/folder --model-path malware_detection_model.pkl
```

The model uses the six feature columns from the notebook workflow:
- `usage_counter`
- `fs_excl_counter`
- `task_size`
- `end_data`
- `policy`
- `nivcsw`

## Run the MLOps stack

Start Elasticsearch, Logstash, Kibana, the MLOps API, and the MLflow UI:

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`:

- `GET /health` checks that the API is running.
- `POST /train` trains the model from the mounted dataset and stores it in the
  persistent `mlops_models` volume.
- `POST /predict` accepts the six feature values and returns a prediction. Train
  a model first.

Example prediction request:

```bash
curl -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"usage_counter":100,"fs_excl_counter":4.5,"task_size":0,"end_data":1,"policy":1,"nivcsw":1}'
```

Training metrics and prediction events are written to the shared `mlops_logs`
volume and indexed by Logstash as `mlops-logs-*`. In Kibana at
`http://localhost:5601`, create a data view for `mlops-logs-*` to explore them.
Structured events are available under `event_data`; for example,
`event_data.event: training_completed` and
`event_data.event: prediction_completed`.

The `mlflow_data` volume persists MLflow tracking data and artifacts.
Elasticsearch, Logstash state, and the trained model are also stored in named
volumes. To intentionally remove persisted data, use
`docker compose down --volumes`.
