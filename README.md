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

## Train the UCI malware models

The separate `hex_malwer_detection.ipynb` workflow uses
`dataset/uci_malware_detection.csv`, which has a `Label` target and 531
numeric feature columns. It trains a regularized decision tree and a
standardized K-nearest-neighbors classifier, evaluates both on the same
stratified 80/20 split, and saves their feature schema and metrics without
replacing the six-feature model used by the API or file scanner:

```bash
python hex_malware_detection.py
```

Override the dataset and output bundle paths when needed:

```bash
python hex_malware_detection.py \
  --dataset dataset/uci_malware_detection.csv \
  --model-path hex_malware_models.pkl
```

The equivalent Make target is `make train_hex_model`. The saved bundle
contains both classifiers under `models`, the ordered `feature_columns`, class
labels, and holdout metrics. Each model's holdout metrics and per-row
predictions are also written to `logs/hex_malware_detection.log`.

## Cluster monitoring notebook

Run `notebooks/Monitoring_Cluster.ipynb` from top to bottom. It reads
`dataset/datacenter_warehouse_50k.csv`, checks the required telemetry columns,
cleans missing/non-numeric model inputs, creates a reproducible proxy outage
target, trains and evaluates a Random Forest, reviews feature importance and
correlations, and compares additional models. The generated outage labels are
demonstration labels based on CPU/memory thresholds with seeded noise; they
are not observed outage records.

Run the script equivalent from the repository root with
`python Monitor_Cluster.py`. It reads `dataset/datacenter_warehouse_50k.csv`
relative to the script location and writes structured evaluation events to
`logs/cluster_monitoring.log`.

## Kibana malware metrics

The `main.py` malware CLI writes its training metrics and scanned-file
predictions to `logs/malwer_detecter.log` by default. The cluster script writes
one event per evaluated model to `logs/cluster_monitoring.log`; those records
include the dataset dimensions, feature columns, standard accuracy/precision/
recall/F1 fields, and confusion-matrix counts. Logstash also reads the notebook
log at `logs/malware_detection_notebook.log`, the API log at
`/app/logs/mlops.log`, and the hex-model log at
`logs/hex_malware_detection.log`. The events share the `logs-*` indices and
typed `event_data` fields (including `event_data.metric_accuracy`,
`event_data.metric_f1`, `event_data.feature_columns`, and the cluster
`event_data.feature_importance` values) rather than creating a separate
Elasticsearch index for each script.

With the Docker Compose stack running, restart Logstash after applying the
pipeline change. Refresh or create the Kibana data view `logs-*` to see new
records. Filter on `event_data.event` for event type and `event_data.model` to
compare models and use `event_data.event` to distinguish script event types.
After changing the Logstash pipeline, restart Logstash and refresh the Kibana
data view so the new typed fields are available. If the saved dashboard is
already imported, update it with
`bash setup/import_kibana_dashboard.sh`.

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
volume and indexed by Logstash as `logs-*`. In Kibana at
`http://localhost:5601`, create a data view for `logs-*` to explore them.
Structured events are available under `event_data`; for example,
`event_data.event: training_completed` and
`event_data.event: prediction_completed`.

The `mlflow_data` volume persists MLflow tracking data and artifacts.
Elasticsearch, Logstash state, and the trained model are also stored in named
volumes. To intentionally remove persisted data, use
`docker compose down --volumes`.
