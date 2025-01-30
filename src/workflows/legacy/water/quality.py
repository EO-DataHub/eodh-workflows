from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import click
import rioxarray  # noqa: F401
from tqdm import tqdm

from src.consts.crs import WGS84
from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.utils.geom import geojson_to_polygon
from src.utils.logging import get_logger
from src.utils.raster import generate_thumbnail_with_continuous_colormap, get_raster_bounds, image_to_base64, save_cog
from src.utils.stac import generate_stac, prepare_stac_asset, prepare_stac_item, prepare_thumbnail_asset
from src.workflows.ds.utils import prepare_data_array, prepare_s2_ard_data_array
from src.workflows.legacy.raster.calculator import query_stac
from src.workflows.spectral.indices import (
    CDOM,
    DOC,
    CyaCells,
    Turbidity,
    resolve_rescale_params,
)

_logger = get_logger(__name__)


@click.command(help="Calculate water quality indices")
@click.option("--stac_collection", required=True, help="The name of the STAC collection to get the data from")
@click.option("--aoi", required=True, help="Area of Interest as GeoJSON")
@click.option("--date_start", required=True, help="Start date for the STAC query")
@click.option("--date_end", help="End date for the STAC query - will use current UTC date if not specified")
@click.option(
    "--limit",
    default=50,
    required=False,
    show_default=True,
    help="Max number of items to process",
)
@click.option(
    "--clip",
    required=False,
    default="False",
    type=click.Choice(["True", "False"], case_sensitive=False),
    help="A flag indicating whether to crop the data to the AOI",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def water_quality(  # noqa: PLR0914, RUF100
    stac_collection: str,
    aoi: str,
    date_start: str,
    date_end: str,
    limit: int = 50,
    output_dir: Path | None = None,
    clip: Literal["True", "False"] = "False",
) -> None:
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_collection": stac_collection,
                "aoi": aoi,
                "date_start": date_start,
                "date_end": date_end,
                "limit": limit,
                "clip": clip,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    aoi_polygon: dict[str, Any] = json.loads(aoi)

    items = query_stac(
        aoi_polygon=aoi_polygon,
        date_end=date_end,
        date_start=date_start,
        stac_collection=stac_collection,
        limit=limit,
    )

    output_items = []
    progress_bar = tqdm(items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        # Generate new Item ID to avoid conflicts if running with scatter operator
        item_id = str(uuid4())

        raster_arr = (
            prepare_data_array(
                item=item,
                bbox=geojson_to_polygon(aoi).bounds if clip == "True" else None,
                assets=["blue", "green", "red", "rededge1", "nir", "scl"],
            )
            if stac_collection == "sentinel-2-l2a"
            else prepare_s2_ard_data_array(
                item=item,
                aoi=aoi_polygon if clip == "True" else None,
            )
        )

        scale, offset = resolve_rescale_params(collection_name=item.collection_id, item_datetime=item.datetime)

        out_item = prepare_stac_item(
            id_item=item_id,
            geometry=get_raster_bounds(raster_arr),
            epsg=raster_arr.rio.crs.to_epsg(),
            transform=list(raster_arr.rio.transform()),
            datetime=item.datetime,
            additional_prop={
                "workflow_metadata": {
                    "stac_collection": stac_collection,
                    "date_start": date_start,
                    "date_end": date_end,
                    "aoi": aoi_polygon,
                },
            },
            assets=None,
        )

        for index_calculator in [
            CDOM(),
            DOC(),
            CyaCells(),
            Turbidity(),
        ]:
            _logger.info("Calculating %s index for item %s", index_calculator.full_name, item.id)
            index_raster = index_calculator.calculate_index(
                raster_arr=raster_arr,
                rescale_factor=scale,
                rescale_offset=offset,
            ).rio.reproject(WGS84)
            raster_path = save_cog(
                arr=index_raster,
                asset_id=f"{item_id}_{index_calculator.name}",
                output_dir=output_dir,
                epsg=WGS84,
            )

            vmin, vmax, _ = index_calculator.typical_range

            if index_calculator.name == "doc":  # Use DOC as item's thumbnail
                mpl_cmap, _ = index_calculator.mpl_colormap
                thumb_fp = output_dir / f"{item_id}.png"
                generate_thumbnail_with_continuous_colormap(
                    data=index_raster,
                    out_fp=thumb_fp,
                    colormap=mpl_cmap,
                    max_val=vmax,
                    min_val=vmin,
                )
                thumb_b64 = image_to_base64(thumb_fp)
                out_item.properties["thumbnail_b64"] = thumb_b64
                out_item.add_asset(key="thumbnail", asset=prepare_thumbnail_asset(thumbnail_path=thumb_fp))

            data_asset = prepare_stac_asset(
                title=index_calculator.full_name,
                file_path=raster_path,
                asset_extra_fields=index_calculator.asset_extra_fields(index_raster),
            )
            out_item.add_asset(index_calculator.name, data_asset)

        output_items.append(out_item)

    generate_stac(
        items=output_items,
        output_dir=output_dir,
        title="EOPro Water Quality calculation",
        description=f"Water Quality calculation with {stac_collection}",
    )
