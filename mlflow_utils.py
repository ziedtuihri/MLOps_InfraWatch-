from contextlib import contextmanager
from typing import Iterator

import mlflow


@contextmanager
def mlflow_run(experiment_name: str, run_name: str) -> Iterator:
    """Start a run in the requested experiment, nesting under an active run."""
    active_run = mlflow.active_run()
    if active_run is None:
        mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name, nested=active_run is not None) as run:
        yield run
