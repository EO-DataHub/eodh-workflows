from __future__ import annotations

import json
from pathlib import Path

import click
import pystac
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_STAC_OUTPUT_DIR_DICT
from src.raster_utils.save import save_cog
from src.raster_utils.thumbnail import generate_thumbnail_with_discrete_classes, image_to_base64
from src.utils.logging import get_logger

_logger = get_logger(__name__)


@click.command(help="Generate thumbnails for items in specific STAC.")
@click.option(
    "--input_stac",
    required=True,
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
def generate_thumbnails(input_stac: Path) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "input_stac": input_stac.as_posix(),
            },
            indent=4,
        ),
    )

    output_dir = LOCAL_STAC_OUTPUT_DIR_DICT["thumbnails"]
    output_dir.mkdir(exist_ok=True, parents=True)

    local_stac = pystac.Catalog.from_file((input_stac / "catalog.json").as_posix())
    local_stac.make_all_asset_hrefs_absolute()

    stac_items = local_stac.get_items()
    progress_bar = tqdm(stac_items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")
        raster_arr = rioxarray.open_rasterio(Path(item.assets["data"].href), masked=True)
        raster_path = save_cog(
            arr=raster_arr, item_id=item.id, epsg=item.properties["proj:epsg"], output_dir=output_dir
        )
        item.assets["data"].href = raster_path.as_posix()

        if "classification:classes" in item.assets["data"].extra_fields:
            thumb_file_path = generate_thumbnail_with_discrete_classes(
                raster_arr,
                raster_path=raster_path,
                classes_list=item.assets["data"].extra_fields["classification:classes"],
                output_dir=raster_path.parent,
            )
            thumb_b64 = image_to_base64(thumb_file_path)
        else:
            error_string = "Generating thumbnails implemented only for classification datasets"
            raise NotImplementedError(error_string)

        item.properties["thumbnail_b64"] = thumb_b64
        item.add_asset(
            key="thumbnail",
            asset=pystac.Asset(
                title="Thumbnail",
                href=thumb_file_path.as_posix(),
                media_type=pystac.MediaType.PNG,
                extra_fields={
                    "size": thumb_file_path.stat().st_size,
                },
                roles=["thumbnail"],
            ),
        )

    local_stac.title = "EOPro Thumbnails Generated"
    local_stac.description = "EOPro Thumbnails Generated"
    local_stac.make_all_asset_hrefs_relative()
    local_stac.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)
