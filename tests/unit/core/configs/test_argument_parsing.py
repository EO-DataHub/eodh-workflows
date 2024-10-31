from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from src.core.configs.argument_parsing import parse_args
from src.core.configs.base import ConfigBase


class TestConfig(ConfigBase):
    a: int
    b: str


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=int)
    parser.add_argument("--b", type=str)
    return parser


@patch("src.core.configs.argument_parsing._logger")
def test_parse_args_correct_parsing(mock_logger: MagicMock, parser: argparse.ArgumentParser) -> None:
    args = ["--a", "123", "--b", "test"]

    with patch("sys.argv", ["test_script.py", *args]):
        config = parse_args(parser, TestConfig)

    assert isinstance(config, TestConfig)
    assert config.a == 123  # noqa: PLR2004
    assert config.b == "test"
    mock_logger.info.assert_called_with("Running with following config: %(cfg)s", {"cfg": config})


@patch("src.core.configs.argument_parsing._logger")
def test_parse_args_unknown_arguments(mock_logger: MagicMock, parser: argparse.ArgumentParser) -> None:
    args = ["--a", "123", "--b", "test", "--unknown", "value"]

    with patch("sys.argv", ["test_script.py", *args]):
        _ = parse_args(parser, TestConfig)
        unknown_args = ["--unknown", "value"]

    mock_logger.info.assert_any_call("Unknown args: %(unknown_args)s", {"unknown_args": unknown_args})
