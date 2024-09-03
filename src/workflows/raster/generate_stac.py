from __future__ import annotations

import datetime as dt
import json
import mimetypes
import time
from pathlib import Path
from typing import Any


def create_stac_item(out_name: str, out_dir: Path | None) -> Path:
    if out_dir is None:
        out_dir = Path.cwd()

    stem = Path(out_name).stem
    now = time.time_ns() / 1_000_000_000
    date_now_dt = dt.datetime.fromtimestamp(now, tz=dt.timezone.utc)
    date_now = date_now_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    size = Path(f"{out_name}").stat().st_size
    mime = mimetypes.guess_type(f"{out_name}")[0]
    data = {
        "stac_version": "1.0.0",
        "id": f"{stem}-{now}",
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-180, -90], [-180, 90], [180, 90], [180, -90], [-180, -90]]],
        },
        "properties": {
            "created": f"{date_now}",
            "datetime": f"{date_now}",
            "updated": f"{date_now}",
        },
        "bbox": [-180, -90, 180, 90],
        "assets": {
            f"{stem}": {
                "type": f"{mime}",
                "roles": ["data"],
                "href": f"{out_name}",
                "file:size": size,
            }
        },
        "links": [
            {"type": "application/json", "rel": "parent", "href": "catalog.json"},
            {"type": "application/geo+json", "rel": "self", "href": f"{stem}.json"},
            {"type": "application/json", "rel": "root", "href": "catalog.json"},
        ],
    }
    with Path(f"{out_dir}/{stem}.json").open(mode="w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return Path(f"{out_dir}/{stem}.json")


def create_stac_catalog_root(paths: list[Path], out_dir: Path | None) -> None:
    if out_dir is None:
        out_dir = Path.cwd()

    data: dict[str, Any] = {
        "stac_version": "1.0.0",
        "id": "catalog",
        "type": "Catalog",
        "description": "Root catalog",
        "links": [],
    }

    for item in paths:
        data["links"].append({"type": "application/geo+json", "rel": "item", "href": f"{item.name}"})
    data["links"].append({"type": "application/json", "rel": "self", "href": "catalog.json"})

    with Path(f"{out_dir}/catalog.json").open(mode="w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
