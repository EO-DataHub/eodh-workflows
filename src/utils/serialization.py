from __future__ import annotations

from datetime import date, datetime
from json import JSONEncoder
from pathlib import Path
from typing import Any


class JsonEncoder(JSONEncoder):
    """Custom JSON encoder that handles datatypes that are not out-of-the-box supported by the `json` package."""

    def default(self, o: Any) -> str:
        if isinstance(o, (date, datetime)):
            return o.isoformat()

        if isinstance(o, Path):
            return o.as_posix()

        return super().default(o)  # type: ignore[no-any-return]
