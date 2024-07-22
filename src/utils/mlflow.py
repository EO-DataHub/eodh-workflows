from __future__ import annotations

import os


def resolve_experiment_name(default_experiment_name: str) -> str:
    """Resolves MLFlow experiment name.

    If environment variable `"MLFLOW_EXPERIMENT_NAME"` is set, then the experiment name
    will be resolved based on this environment variable. Otherwise, the default experiment name, passed as
    and argument will be used.

    Useful when working with Azure ML.

    Notes:
        This function will set the environment variable `"MLFLOW_EXPERIMENT_NAME"` if it is not set.

    Args:
        default_experiment_name: The default experiment name to use if environment variable is not set.

    Returns: The resolved experiment name.

    Examples:
        When env variable is unset, the default exp name passed as argument will be used.

        >>> del os.environ["MLFLOW_EXPERIMENT_NAME"]
        >>> resolve_experiment_name("custom-mlflow-experiment-name")
        'custom-mlflow-experiment-name'

        Otherwise, the default exp name indicated by the env var will be used.

        >>> os.environ["MLFLOW_EXPERIMENT_NAME"] = "env-defined-mlflow-experiment-name"
        >>> resolve_experiment_name("different-mlflow-experiment-name")
        'env-defined-mlflow-experiment-name'

    """
    if os.environ.get("MLFLOW_EXPERIMENT_NAME", None) is None:
        os.environ["MLFLOW_EXPERIMENT_NAME"] = default_experiment_name
    return os.environ["MLFLOW_EXPERIMENT_NAME"]


def run_id_from_context() -> str | None:
    """Resolves the MLFlow Run ID from the context.

    Returns:
        The MLFlow Run ID based on `"MLFLOW_RUN_ID"` environment variable. If not set, returns `None`.

    """
    return os.environ.get("MLFLOW_RUN_ID", None)
