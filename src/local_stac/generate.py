from __future__ import annotations

import datetime as dt
from typing import Any

import pystac
from pystac.extensions.projection import ProjectionExtension
from shapely.geometry import Polygon, mapping
from pathlib import Path


LOCAL_STAC_OUTPUT_DIR = Path.cwd() / "data" / "stac-catalog"

def generate_stac(
    items: list[pystac.Item],
    geometry: Polygon,
    start_date: str,
    end_date: str,
    description: str = "Outputs from the job processed on ADES",
) -> None:
    catalog = pystac.Catalog(id="catalog", description=description)

    collection = pystac.Collection(
        id="collection",
        description=description,
        extent=pystac.Extent(
            spatial=pystac.SpatialExtent([list(geometry.bounds)]),
            temporal=pystac.TemporalExtent([
                [dt.datetime.fromisoformat(start_date), dt.datetime.fromisoformat(end_date)]
            ]),
        ),
    )

    catalog.add_child(collection)

    for item in items:
        collection.add_item(item)

    LOCAL_STAC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog.normalize_and_save(str(LOCAL_STAC_OUTPUT_DIR), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def prepare_stac_item(
    file_path: Path,
    id_item: str,
    geometry: Polygon,
    epsg: int,
    transform: list[float],
    datetime: str,
    additional_prop: dict[str, dict[str, Any]],
    asset_extra_fields: dict[str, list[dict[str, Any]]],
) -> pystac.Item:
    item = pystac.Item(
        id=id_item,
        geometry=mapping(geometry),
        bbox=geometry.bounds,
        datetime=datetime,
        properties=additional_prop,
    )

    projection = ProjectionExtension.ext(item, add_if_missing=True)

    projection.epsg = epsg
    projection.transform = transform

    item.add_asset(
        key="data", asset=pystac.Asset(href=f"../../{file_path.name}", media_type=pystac.MediaType.COG, extra_fields=asset_extra_fields)
    )

    return item
