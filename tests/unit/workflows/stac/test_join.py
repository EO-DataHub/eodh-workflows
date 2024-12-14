from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pystac
from pystac import Asset, Catalog, Item

from src.workflows.stac.join import merge_stac_catalogs

if TYPE_CHECKING:
    from pathlib import Path


def create_dummy_catalog(catalog_name: str, items_and_assets: dict[str, Any], output_dir: Path) -> Path:
    catalog_path = (output_dir / catalog_name).resolve().absolute()
    catalog = Catalog(id=catalog_name, description=f"Dummy {catalog_name} catalog")
    for item_id, assets in items_and_assets.items():
        item = Item(
            id=item_id,
            geometry=None,
            bbox=None,
            datetime=datetime.now(tz=timezone.utc),
            properties={},
        )
        for asset_key, asset_filename in assets.items():
            asset_path = catalog_path / item_id / asset_filename
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_text(f"Dummy content for {asset_filename}")
            item.add_asset(key=asset_key, asset=Asset(href=asset_path.as_posix(), media_type="text/plain"))
        catalog.add_item(item)
    catalog.normalize_and_save(
        root_href=catalog_path.as_posix(),
        catalog_type=pystac.CatalogType.SELF_CONTAINED,
    )
    return catalog_path


def test_merge_stac_catalogs(tmp_path: Path) -> None:
    # Arrange
    catalog1_path = create_dummy_catalog(
        catalog_name="ndvi_catalog",
        items_and_assets={
            "item1": {"ndvi_asset": "ndvi1.txt"},
            "item2": {"ndvi_asset": "ndvi2.txt"},
        },
        output_dir=tmp_path,
    )
    catalog2_path = create_dummy_catalog(
        catalog_name="evi_catalog",
        items_and_assets={
            "item1": {"evi_asset": "evi1.txt"},
            "item3": {"evi_asset": "evi3.txt"},
        },
        output_dir=tmp_path,
    )
    output_path = tmp_path / "merged_catalog"

    # Act
    merge_stac_catalogs(catalog1_path / "catalog.json", catalog2_path / "catalog.json", output_path)

    # Assert
    merged_catalog = Catalog.from_file(output_path / "catalog.json")

    # Check the items in the merged catalog
    item_ids = [item.id for item in merged_catalog.get_items()]
    assert set(item_ids) == {"item1", "item2", "item3"}

    # Check assets for each item
    item1 = next(merged_catalog.get_items("item1"))
    assert "ndvi_asset" in item1.assets
    assert "evi_asset" in item1.assets
    assert (output_path / "source_data/item1/ndvi1.txt").exists()
    assert (output_path / "source_data/item1/evi1.txt").exists()

    item2 = next(merged_catalog.get_items("item2"))
    assert "ndvi_asset" in item2.assets
    assert (output_path / "source_data/item2/ndvi2.txt").exists()

    item3 = next(merged_catalog.get_items("item3"))
    assert "evi_asset" in item3.assets
    assert (output_path / "source_data/item3/evi3.txt").exists()
