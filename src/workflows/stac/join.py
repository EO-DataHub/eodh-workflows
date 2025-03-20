from __future__ import annotations

import json
import shutil
from pathlib import Path

import click
from pystac import Asset, Catalog, CatalogType
from tqdm import tqdm

from src.consts.directories import LOCAL_DATA_DIR
from src.utils.logging import get_logger
from src.utils.stac import write_local_stac

_logger = get_logger(__name__)


@click.command(
    help="Joins two STAC catalogs into a single catalog",
)
@click.option(
    "--stac_catalog_dir_1",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the first STAC catalog directory",
)
@click.option(
    "--stac_catalog_dir_2",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the second STAC catalog directory",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def join(stac_catalog_dir_1: Path, stac_catalog_dir_2: Path, output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_catalog_1": stac_catalog_dir_1.as_posix(),
                "stac_catalog_2": stac_catalog_dir_2.as_posix(),
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    # Verify catalog.json exists
    if not (stac_catalog_dir_1 / "catalog.json").exists():
        msg = f"catalog.json does not exist under {stac_catalog_dir_1.as_posix()}"
        raise ValueError(msg)
    if not (stac_catalog_dir_2 / "catalog.json").exists():
        msg = f"catalog.json does not exist under {stac_catalog_dir_2.as_posix()}"
        raise ValueError(msg)

    output_dir = output_dir or LOCAL_DATA_DIR / "stac-join"
    output_dir.mkdir(exist_ok=True, parents=True)
    merge_stac_catalogs(
        catalog1_path=stac_catalog_dir_1 / "catalog.json",
        catalog2_path=stac_catalog_dir_2 / "catalog.json",
        output_dir=output_dir,
    )


@click.command(
    help="Joins two STAC catalogs into a single catalog",
)
@click.option(
    "--stac_catalog_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    multiple=True,
    required=True,
    help="Path to the first STAC catalog directory",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def join_v2(stac_catalog_dir: list[Path], output_dir: Path | None = None) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_catalog_dir": [d.as_posix() for d in stac_catalog_dir],
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    # Verify catalog.json exists
    for cat in stac_catalog_dir:
        if not (cat / "catalog.json").exists():
            msg = f"catalog.json does not exist under {cat.as_posix()}"
            raise ValueError(msg)

    output_dir = output_dir or LOCAL_DATA_DIR / "stac-join"
    output_dir.mkdir(exist_ok=True, parents=True)

    # Handle single catalog
    if len(stac_catalog_dir) == 1:
        _logger.info("Single STAC catalog passed as input. Nothing to do... Copying STAC dir as is to output dir")
        shutil.copytree(stac_catalog_dir[0], output_dir)

    merge_stac_catalogs_v2(
        stac_catalog_dirs=stac_catalog_dir,
        output_dir=output_dir,
    )


def merge_stac_catalogs(catalog1_path: Path, catalog2_path: Path, output_dir: Path) -> None:
    # Load the catalogs
    catalog1 = Catalog.from_file(catalog1_path.resolve().absolute().as_posix())
    catalog1.make_all_asset_hrefs_absolute()
    catalog2 = Catalog.from_file(catalog2_path.resolve().absolute().as_posix())
    catalog2.make_all_asset_hrefs_absolute()
    output_dir = output_dir.resolve().absolute()

    # Create a new catalog for the merged output
    merged_catalog = Catalog(
        id="merged-catalog", description="Merged STAC catalog combining assets from two input catalogs"
    )

    # Helper function to copy assets to the output directory
    def copy_asset(asset: Asset, item_id: str, output_base: Path) -> Asset:
        # Determine the destination directory for the asset
        item_dir = output_base / "source_data" / item_id
        item_dir.mkdir(exist_ok=True, parents=True)

        # Determine the new HREF and copy the file
        new_href = item_dir / Path(asset.href).name
        shutil.copy(asset.href, new_href)

        # Update the asset with the new HREF
        asset.href = new_href.absolute().as_posix()
        return asset

    # Index items in the second catalog for easier matching
    catalog2_items = {item.id: item for item in catalog2.get_items()}

    # Iterate through items in the first catalog
    for item1 in catalog1.get_items():
        merged_item = item1.clone()  # Start with a clone of item1
        item2 = catalog2_items.get(item1.id)

        # Copy assets from item1
        merged_item.assets = {
            key: copy_asset(asset=asset, item_id=item1.id, output_base=output_dir)
            for key, asset in item1.assets.items()
        }

        # Merge and copy assets from item2, if it exists
        if item2:
            for key, asset in item2.assets.items():
                # Add or overwrite assets in the merged item
                merged_item.add_asset(key, copy_asset(asset=asset, item_id=item1.id, output_base=output_dir))

        # Add the merged item to the merged catalog
        merged_catalog.add_item(merged_item)

    # Add any additional items from catalog2 not in catalog1
    catalog1_item_ids = {item.id for item in catalog1.get_items()}
    for item_id, item in catalog2_items.items():
        if item_id not in catalog1_item_ids:
            # Clone the item and copy its assets
            cloned_item = item.clone()
            cloned_item.assets = {
                key: copy_asset(asset=asset, item_id=item.id, output_base=output_dir)
                for key, asset in item.assets.items()
            }
            merged_catalog.add_item(cloned_item)

    # Save the merged catalog to the output path
    output_dir.mkdir(exist_ok=True, parents=True)
    write_local_stac(merged_catalog, output_dir, "EOPro Merged Catalog", "EOPro Merged Catalog")


def merge_stac_catalogs_v2(stac_catalog_dirs: list[Path], output_dir: Path) -> None:
    # Create an empty root catalog for the merged output
    merged_catalog = Catalog(id="merged-catalog", description="Merged STAC Catalog")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_data_dir = output_dir / "source_data"
    source_data_dir.mkdir(parents=True, exist_ok=True)

    for dir_path in tqdm(stac_catalog_dirs, desc="Joining STAC Catalogs"):
        catalog_path = dir_path / "catalog.json"

        if not catalog_path.exists():
            click.echo(f"Skipping {dir_path} (catalog.json not found)")
            continue

        # Load the catalog
        input_catalog = Catalog.from_file(str(catalog_path))
        input_catalog.make_all_asset_hrefs_absolute()

        # Traverse and process each item
        for item in input_catalog.get_items(recursive=True):
            # Create a folder for the item's assets in the source_data directory
            item_assets_dir = source_data_dir / item.id
            item_assets_dir.mkdir(parents=True, exist_ok=True)

            # Copy each asset to the new folder
            for asset in item.assets.values():
                asset_path = Path(asset.href)
                if asset_path.exists():
                    new_asset_path = item_assets_dir / asset_path.name
                    shutil.copy2(asset_path, new_asset_path)
                    asset.href = new_asset_path.absolute().as_posix()

            # Add the item to the merged catalog
            merged_catalog.add_item(item)

    # Save the merged catalog to the output directory
    merged_catalog.make_all_asset_hrefs_relative()
    merged_catalog.normalize_and_save(output_dir.as_posix(), catalog_type=CatalogType.SELF_CONTAINED)
