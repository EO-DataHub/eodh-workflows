from __future__ import annotations

import pathlib
import typing

import pytest

from src import consts

if typing.TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.python import Function

MARKERS = ["unit", "integration", "e2e"]


def pytest_collection_modifyitems(config: Config, items: list[Function]) -> None:  # noqa: ARG001
    rootdir = pathlib.Path(consts.directories.ROOT_DIR)
    for item in items:
        rel_path = pathlib.Path(item.fspath).relative_to(rootdir)
        mark_name = rel_path.as_posix().split("/")[1]
        if mark_name in MARKERS:
            mark = getattr(pytest.mark, mark_name)
            item.add_marker(mark)
