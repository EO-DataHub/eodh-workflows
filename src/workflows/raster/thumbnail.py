from __future__ import annotations

import json
import shutil
from pathlib import Path

import click
import rioxarray
from tqdm import tqdm

from src.consts.directories import LOCAL_DATA_DIR
from src.utils.logging import get_logger
from src.utils.raster import (
    generate_thumbnail_as_grayscale_image,
    generate_thumbnail_rgb,
    generate_thumbnail_with_continuous_colormap,
    generate_thumbnail_with_discrete_classes,
    image_to_base64,
)
from src.utils.stac import prepare_thumbnail_asset, read_local_stac, write_local_stac

_logger = get_logger(__name__)


@click.command(help="Generate thumbnails for items in STAC catalog")
@click.option(
    "--data_dir",
    required=True,
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the local STAC folder",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def generate_thumbnail_for_stac_items(
    data_dir: Path,
    output_dir: Path | None = None,
) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "data_dir": data_dir.as_posix(),
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    output_dir = output_dir or LOCAL_DATA_DIR / "raster-thumbnail"
    output_dir.mkdir(exist_ok=True, parents=True)

    local_stac = read_local_stac(data_dir)
    local_stac.make_all_asset_hrefs_absolute()

    for item in tqdm(list(local_stac.get_items(recursive=True)), desc="Processing STAC items"):
        asset_dir = Path(next(iter(item.assets.values())).href).parent
        asset_out_dir = output_dir / asset_dir.relative_to(data_dir.absolute())
        asset_out_dir.mkdir(exist_ok=True, parents=True)

        for asset in item.assets.values():
            asset_fp = Path(asset.href)
            shutil.copy(asset_fp, asset_out_dir / asset_fp.name)
            asset.href = (asset_out_dir / asset_fp.name).absolute().as_posix()

        if "visual" in item.assets:
            asset_key = "visual"

        elif "data" in item.assets:
            asset_key = "data"

        else:
            asset_key = next(iter(item.assets))

        asset = item.assets[asset_key]
        asset_dict = asset.to_dict()

        arr = rioxarray.open_rasterio(asset_dict["href"])
        thumb_fp = (asset_out_dir / f"{Path(asset_dict['href']).stem}_thumbnail.png").absolute()

        if asset_key == "visual":
            generate_thumbnail_rgb(arr, out_fp=thumb_fp)

        if "colormap" in asset_dict:
            cmap_details = asset_dict["colormap"]
            mpl_cmap = cmap_details["mpl_equivalent_cmap"]
            vmin = cmap_details["min"]
            vmax = cmap_details["max"]
            generate_thumbnail_with_continuous_colormap(
                arr,
                out_fp=thumb_fp,
                colormap=mpl_cmap,
                max_val=vmax,
                min_val=vmin,
            )

        elif "classification:classes" in asset_dict:
            generate_thumbnail_with_discrete_classes(
                arr,
                out_fp=thumb_fp,
                classes_list=asset_dict["classification:classes"],
            )

        else:
            generate_thumbnail_as_grayscale_image(arr, out_fp=thumb_fp)

        thumb_b64 = image_to_base64(thumb_fp)
        item.properties["thumbnail_b64"] = thumb_b64
        item.add_asset("thumbnail", prepare_thumbnail_asset(thumbnail_path=thumb_fp))

    write_local_stac(local_stac, output_dir, local_stac.title, local_stac.description)
