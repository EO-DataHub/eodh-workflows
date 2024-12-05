from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT_DIR / "tests"
DATA_DIR = ROOT_DIR / "data"
SRC_DIR = ROOT_DIR / "src"
LOCAL_STAC_OUTPUT_DIR_DICT = {
    "download": Path.cwd() / "data" / "downloaded",
    "clip": Path.cwd() / "data" / "clipped",
    "lulc_change": Path.cwd() / "data" / "lulc_change",
    "thumbnails": Path.cwd() / "data" / "thumbnails",
}
LOCAL_STAC_OUTPUT_DIR = Path.cwd() / "data" / "stac-catalog"
