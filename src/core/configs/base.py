from __future__ import annotations

from pydantic import BaseModel


class ConfigBase(BaseModel):
    """A base class for all entrypoint config classes."""

    def __str__(self) -> str:
        return self.model_dump_json(indent=4)  # type: ignore[no-any-return]
