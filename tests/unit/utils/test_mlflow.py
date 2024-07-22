from __future__ import annotations

import os
from unittest.mock import patch

from src.utils.mlflow import resolve_experiment_name, run_id_from_context


def test_resolve_experiment_name_env_set() -> None:
    with patch.dict(os.environ, {"MLFLOW_EXPERIMENT_NAME": "env-defined-mlflow-experiment-name"}):
        result = resolve_experiment_name("default-mlflow-experiment-name")
        assert result == "env-defined-mlflow-experiment-name"


def test_resolve_experiment_name_env_not_set() -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = resolve_experiment_name("default-mlflow-experiment-name")
        assert result == "default-mlflow-experiment-name"
        assert os.environ["MLFLOW_EXPERIMENT_NAME"] == "default-mlflow-experiment-name"


def test_resolve_experiment_name_env_unset_then_set() -> None:
    with patch.dict(os.environ, {}, clear=True):
        # First call with no environment variable set
        result1 = resolve_experiment_name("default-mlflow-experiment-name")
        assert result1 == "default-mlflow-experiment-name"
        # Simulate setting the environment variable
        os.environ["MLFLOW_EXPERIMENT_NAME"] = "new-env-defined-mlflow-experiment-name"
        # Second call should return the new set environment variable value
        result2 = resolve_experiment_name("different-mlflow-experiment-name")
        assert result2 == "new-env-defined-mlflow-experiment-name"


def test_run_id_from_context_set() -> None:
    with patch.dict(os.environ, {"MLFLOW_RUN_ID": "1234"}):
        result = run_id_from_context()
        assert result == "1234"


def test_run_id_from_context_not_set() -> None:
    with patch.dict(os.environ, {}, clear=True):
        result = run_id_from_context()
        assert result is None
