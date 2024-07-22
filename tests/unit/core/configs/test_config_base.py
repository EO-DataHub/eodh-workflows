from __future__ import annotations

from src.core.configs.base import ConfigBase


class DummyConfig(ConfigBase):
    x: int
    y: float
    z: str


def test_config_base_str() -> None:
    cfg = DummyConfig(x=1, y=2.0, z="3")
    assert str(cfg) == '{\n    "x": 1,\n    "y": 2.0,\n    "z": "3"\n}'
