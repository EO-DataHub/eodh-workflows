from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pystac
from pystac.extensions.projection import ProjectionExtension
from shapely.geometry import Polygon, mapping

if TYPE_CHECKING:
    from pathlib import Path


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


def prepare_stac_asset(
    file_path: Path,
    title: str | None = None,
    description: str | None = None,
    asset_extra_fields: dict[str, Any] | None = None,
) -> pystac.Asset:
    if asset_extra_fields is None:
        asset_extra_fields = {}

    if "size" not in asset_extra_fields:
        asset_extra_fields["size"] = file_path.stat().st_size

    return pystac.Asset(
        title=title,
        description=description,
        href=f"../{file_path.name}",
        media_type=pystac.MediaType.COG,
        extra_fields=asset_extra_fields,
        roles=["data"],
    )


def prepare_thumbnail_asset(thumbnail_path: Path) -> pystac.Asset:
    return pystac.Asset(
        title="Thumbnail",
        href=f"../{thumbnail_path.name}",
        media_type=pystac.MediaType.PNG,
        extra_fields={
            "size": thumbnail_path.stat().st_size,
        },
        roles=["thumbnail"],
    )


def prepare_stac_item(
    id_item: str,
    geometry: Polygon,
    epsg: int,
    transform: list[float],
    datetime: str,
    additional_prop: dict[str, Any],
    assets: dict[str, pystac.Asset] | None = None,
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

    if assets:
        for asset_key, asset in assets.items():
            item.add_asset(key=asset_key, asset=asset)

    return item
