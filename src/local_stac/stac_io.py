from __future__ import annotations

from typing import TYPE_CHECKING

import pystac

if TYPE_CHECKING:
    from pathlib import Path


def read_local_stac(input_stac_path: Path) -> pystac.Catalog:
    stac = pystac.Catalog.from_file((input_stac_path / "catalog.json").as_posix())
    stac.make_all_asset_hrefs_absolute()
    return stac


def write_local_stac(stac: pystac.Catalog, output_stac_path: Path, title: str, description: str) -> None:
    stac.title = title
    stac.description = description
    stac.make_all_asset_hrefs_relative()
    stac.normalize_and_save(output_stac_path.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)
