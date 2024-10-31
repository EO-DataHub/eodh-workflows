from __future__ import annotations

from pathlib import Path
from typing import Any

import pystac
from pystac.extensions.projection import ProjectionExtension
from shapely.geometry import Polygon, mapping

LOCAL_STAC_OUTPUT_DIR = Path.cwd() / "data" / "stac-catalog"


def generate_stac(
    items: list[pystac.Item],
    output_dir: Path,
    title: str = "Catalog",
    description: str = "Outputs from the job processed on ADES",
) -> None:
    catalog = pystac.Catalog(id="catalog", title=title, description=description)

    # Adding a collection is not supported by ADES
    # https://github.com/EO-DataHub/platform-bugs/issues/31

    for item in items:
        catalog.add_item(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    catalog.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def prepare_stac_item(
    file_path: Path,
    id_item: str,
    geometry: Polygon,
    epsg: int,
    transform: list[float],
    datetime: str,
    additional_prop: dict[str, Any],
    asset_extra_fields: dict[str, list[dict[str, Any]]],
    thumbnail_path: Path | None = None,
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
        key="data",
        asset=pystac.Asset(
            href=f"../{file_path.name}", media_type=pystac.MediaType.COG, extra_fields=asset_extra_fields
        ),
    )
    if thumbnail_path:
        item.add_asset(
            key="thumbnail", asset=pystac.Asset(href=f"../{thumbnail_path.name}", media_type=pystac.MediaType.PNG)
        )

    return item
