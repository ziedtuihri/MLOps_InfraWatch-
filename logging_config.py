import logging
import os


def setup_logging(log_file="mlflow.log", level=logging.INFO):
    """Configure the application logger once and return it."""
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )

    logger = logging.getLogger("mlflow_app")
    logger.setLevel(level)
    return logger


def get_logger(name="mlflow_app"):
    """Return a logger instance for the given name."""
    return logging.getLogger(name)
