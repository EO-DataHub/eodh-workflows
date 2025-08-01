from __future__ import annotations

import logging
import time
from functools import wraps
from typing import TYPE_CHECKING, TypeVar

from typing_extensions import ParamSpec

from eodh_workflows import consts

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")
P = ParamSpec("P")


def get_logger(name: str, log_level: int | str = logging.INFO) -> logging.Logger:
    """Builds a `Logger` instance with provided name and log level.

    Args:
        name: The name for the logger.
        log_level: The default log level.

    Returns:
        The logger.

    """
    logger = logging.getLogger(name=name)
    logger.setLevel(log_level)

    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt=consts.logging.FORMAT)
    stream_handler.setFormatter(fmt=formatter)
    logger.addHandler(stream_handler)

    return logger


_timed_logger = get_logger("timed", log_level=logging.INFO)


def timed[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """This decorator prints the execution time for the decorated function.

    Args:
        func: The function to wrap.

    Returns:
        Wrapper around the function.

    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        _timed_logger.info("%(func_name)s is running...", {"func_name": func.__qualname__})
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        _timed_logger.info(
            "%(func_name)s ran in %(execution_time)s",
            {
                "func_name": func.__qualname__,
                "execution_time": f"{(end - start):.4f}",
            },
        )
        return result

    return wrapper
