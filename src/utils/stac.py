from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pystac
from pystac.extensions.projection import ProjectionExtension
from shapely import Polygon
from shapely.geometry import mapping
from shapely.geometry.geo import shape

if TYPE_CHECKING:
    from pathlib import Path


def read_local_stac(input_stac_path: Path) -> pystac.Catalog:
    stac = pystac.Catalog.from_file((input_stac_path / "catalog.json").as_posix())
    stac.make_all_asset_hrefs_absolute()
    return stac


def write_local_stac(stac: pystac.Catalog, output_stac_path: Path, title: str, description: str) -> None:
    stac.set_self_href(output_stac_path.as_posix())
    stac.title = title
    stac.description = description
    stac.make_all_asset_hrefs_relative()
    stac.normalize_and_save(output_stac_path.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def generate_stac(
    items: list[pystac.Item],
    output_dir: Path,
    title: str = "Catalog",
    description: str = "Outputs from the job processed on ADES",
) -> None:
    catalog = pystac.Catalog(id="", title=title, description=description, href=output_dir.as_posix())

    for item in items:
        catalog.add_item(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    catalog.make_all_asset_hrefs_relative()
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
        href=file_path.absolute().as_posix(),
        media_type=pystac.MediaType.COG,
        extra_fields=asset_extra_fields,
        roles=["data"],
    )


def prepare_thumbnail_asset(thumbnail_path: Path) -> pystac.Asset:
    return pystac.Asset(
        title="Thumbnail",
        href=thumbnail_path.absolute().as_posix(),
        media_type=pystac.MediaType.PNG,
        extra_fields={
            "size": thumbnail_path.stat().st_size,
        },
        roles=["thumbnail"],
    )


def prepare_stac_item(
    id_item: str,
    geometry: Polygon | dict[str, Any],
    epsg: int,
    transform: list[float],
    datetime: str,
    additional_prop: dict[str, Any] | None = None,
    assets: dict[str, pystac.Asset] | None = None,
) -> pystac.Item:
    item = pystac.Item(
        id=id_item,
        geometry=mapping(geometry) if isinstance(geometry, Polygon) else geometry,
        bbox=geometry.bounds if isinstance(geometry, Polygon) else shape(geometry).bounds,
        datetime=datetime,
        properties=additional_prop or {},
    )

    projection = ProjectionExtension.ext(item, add_if_missing=True)

    projection.epsg = epsg
    projection.transform = transform

    if assets:
        for asset_key, asset in assets.items():
            item.add_asset(key=asset_key, asset=asset)

    return item


def prepare_local_stac(
    items_paths: list[Path],
    title: str,
    description: str,
) -> pystac.Catalog:
    catalog = pystac.Catalog(id="", title=f"{title} Catalog", description=description)

    # Add items to catalog
    for item_path in items_paths:
        with item_path.open("r", encoding="utf-8") as f:
            item = pystac.Item.from_dict(json.load(f))
            item.links = []
            item.set_self_href(item_path.absolute().as_posix())
        catalog.add_item(item)
        item_path.unlink()

    catalog.make_all_asset_hrefs_relative()

    return catalog
