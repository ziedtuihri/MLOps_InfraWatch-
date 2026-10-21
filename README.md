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

## ElasticNet regression metrics

Run the Iris ElasticNet example to log holdout RMSE and R-squared in the
`ElasticNet Iris Regression` MLflow experiment:

```bash
make train_iris_model
```

The run logs the fitted model, training data lineage, and both metrics against
the held-out Iris dataset. It also writes a structured evaluation event to
`logs/elasticnet_iris.log`, which Logstash indexes for the Kibana `logs-*` data
view. The metrics are available as `event_data.metric_rmse` and
`event_data.metric_r2`.

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
log at `logs/malware_detection_notebook.log` and the API log at
`/app/logs/mlops.log`. The three Python scripts write to separate daily indices:
`logs-malwer-detecter-*`, `logs-hex-malware-detection-*`, and
`logs-cluster-monitoring-*`. All match the `logs-*` Kibana data view and index
template. Structured event values such as the model name are available under
`event_data.model`; the source script is available as the top-level `script`
field.

With the Docker Compose stack running, restart Logstash after applying the
pipeline change. Refresh or create the Kibana data view `logs-*` to see new
records. Filter on `event_data.event` for event type and `event_data.model` to
compare models and use `event_data.event` to distinguish script event types.
After changing the Logstash pipeline, restart Logstash and refresh the Kibana
data view so the new typed fields are available. If the saved dashboard is
already imported, update it with
`bash setup/import_kibana_dashboard.sh`.

## MLflow training experiments

The standalone training workflows log to separate MLflow experiments:
`Malware Detection` (`main.py`), `UCI Malware Detection`
(`hex_malware_detection.py`), `Datacenter Outage Prediction`
(`Monitor_Cluster.py`), and `ElasticNet Iris Regression`
(`elasticnet_iris.py`). The malware and datacenter runs record model
parameters, training data lineage, holdout metrics, evaluation reports, feature
columns, and a scikit-learn model artifact. The Iris run logs RMSE and R-squared
against its held-out dataset with the metrics linked to its logged model.
Training also registers the malware and datacenter models in the Model
Registry (`malware-detection-model`, `uci-malware-decision_tree`,
`uci-malware-knn`, and one `datacenter-outage-*` model per estimator). The
malware scanner artifact includes its fitted scaler so it accepts the original
feature values.

Docker Compose serves the checked-in SQLite tracking store and its associated
`mlruns/` artifacts at `http://localhost:5000`. To make host-run training
scripts write to the same store, set the tracking URI before running them:

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
python main.py --dataset dataset/malwareDataset.csv
```

Without `MLFLOW_TRACKING_URI`, MLflow uses its local default store, which is
separate from the Compose UI. For LAN access, the Compose defaults include the observed origin
`http://192.168.100.77:5000`. If the host address changes, set
`MLFLOW_SERVER_CORS_ALLOWED_ORIGINS` in `.env` to the exact trusted browser
origins, then recreate the `mlopsapp` service. Keep this list limited to
origins you trust.

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

MLflow tracking data and artifacts persist in `mlflow.db` and `mlruns/` in the
project directory. Elasticsearch, Logstash state, logs, and the trained model
are stored in named volumes. `docker compose down --volumes` removes the named
volumes; it does not remove the MLflow files in the project directory.

## Ansible automation

`ansible/site.yml` runs selected Makefile workflows on the local machine.
Install Ansible and run a tag to choose the desired steps; for example:

```bash
ansible-playbook ansible/site.yml --tags setup,quality,training,tests
ansible-playbook ansible/site.yml --tags stack
```

Available tags are `setup` (`make install`), `quality` (`make check`),
`training` (the malware, UCI, and Iris training targets), `tests` (`make test`),
and `stack` (`make up`). The stack starts detached before training and Ansible
waits for the MLflow tracking server. Selecting `training` also starts and
waits for the stack, and configures the training runs to log to its MLflow
server. Running the playbook without tags runs every listed step in order.

The `quality` step checks formatting, lint, and security for the project-root
Python files without changing them. Run `make format` separately to apply
formatting.

To run these steps from a local web interface, install Ansible on the host and
start the UI from the project root:

```bash
make install
make ansible-ui
```

Open `http://127.0.0.1:8080` to select individual tagged steps or run the whole
playbook. The page displays the active status, exit code, and recent Ansible
output. The runner binds only to localhost and allows one playbook run at a
time.
