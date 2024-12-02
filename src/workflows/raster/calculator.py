from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Literal

import click
import rioxarray
from pystac_client import Client
from tqdm import tqdm

from src import consts
from src.consts.crs import WGS84
from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.generate import generate_stac, prepare_stac_item
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.raster_utils.thumbnail import (
    generate_thumbnail_with_continuous_colormap,
    image_to_base64,
)
from src.utils.logging import get_logger
from src.workflows.raster.indices import SPECTRAL_INDICES

warnings.filterwarnings("ignore", category=UserWarning, message="The argument 'infer_datetime_format'")

_logger = get_logger(__name__)
JS_CM_TO_MPL_CL_LOOKUP = {
    "RdBu": "RdBu",
    "velocity-green": "YlGn",
    "jet": "jet",
}
DATASET_TO_CATALOG_LOOKUP = {"sentinel-2-l2a": "supported-datasets/earth-search-aws"}


@click.command(help="Calculate spectral index")
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
    "--index",
    default="NDVI",
    type=click.Choice(SPECTRAL_INDICES, case_sensitive=False),
    show_default=True,
    help="The spectral index to calculate",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def calculate(
    stac_collection: str,
    aoi: str,
    date_start: str,
    date_end: str,
    index: str,
    limit: int = 50,
    output_dir: Path | None = None,
    clip: Literal["True", "False"] = "False",
) -> None:
    index = index.lower()
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_collection": stac_collection,
                "aoi": aoi,
                "date_start": date_start,
                "date_end": date_end,
                "index": index,
                "limit": limit,
                "clip": clip,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )
    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    if stac_collection not in consts.stac.STAC_COLLECTIONS:
        msg = (
            f"Unknown STAC collection provided: `{stac_collection}`. "
            f"Available collections: {', '.join(consts.stac.STAC_COLLECTIONS)}"
        )
        raise ValueError(msg)

    index_calculator = SPECTRAL_INDICES[index]
    if stac_collection not in index_calculator.collection_assets_to_use:
        msg = f"Calculating `{index}` index is not possible for STAC collection `{stac_collection}`"
        raise ValueError(msg)

    aoi_polygon = json.loads(aoi)

    # Connect to STAC API
    catalog = Client.open(
        f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/{DATASET_TO_CATALOG_LOOKUP[stac_collection]}"
    )

    # Define your search with CQL2 syntax
    filter_spec = {
        "op": "and",
        "args": [
            {"op": "s_intersects", "args": [{"property": "geometry"}, aoi_polygon]},
            {"op": "=", "args": [{"property": "collection"}, stac_collection]},
        ],
    }
    if date_start:
        filter_spec["args"].append({"op": ">=", "args": [{"property": "datetime"}, date_start]})  # type: ignore[attr-defined]
    if date_end:
        filter_spec["args"].append({"op": "<=", "args": [{"property": "datetime"}, date_end]})  # type: ignore[attr-defined]
    search = catalog.search(
        collections=[stac_collection],
        filter_lang="cql2-json",
        filter=filter_spec,
        max_items=limit,
    )

    output_items = []
    progress_bar = tqdm(sorted(search.items(), key=lambda x: x.datetime), desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        raster_path = output_dir / f"{item.id}.tif"
        if raster_path.exists():
            _logger.info("%s already exists. Loading....", raster_path.as_posix())
            index_raster = rioxarray.open_rasterio(raster_path)
        else:
            index_raster = index_calculator.compute(
                item=item,
                bbox=gejson_to_polygon(aoi).bounds if clip == "True" else None,
                collection_name=stac_collection,
            )
            raster_path = save_cog(arr=index_raster, item_id=item.id, output_dir=output_dir, epsg=WGS84)

        vmin, vmax, intervals = index_calculator.typical_range
        mpl_cmap, _ = index_calculator.mpl_colormap
        js_cmap, cmap_reversed = index_calculator.js_colormap
        thump_fp = generate_thumbnail_with_continuous_colormap(
            index_raster,
            raster_path=raster_path,
            output_dir=output_dir,
            colormap=mpl_cmap,
            max_val=vmax,
            min_val=vmin,
        )
        thumb_b64 = image_to_base64(thump_fp)

        output_items.append(
            prepare_stac_item(
                file_path=raster_path,
                title=index_calculator.full_name,
                thumbnail_path=thump_fp,
                id_item=item.id,
                geometry=get_raster_bounds(index_raster),
                epsg=index_raster.rio.crs.to_epsg(),
                transform=list(index_raster.rio.transform()),
                datetime=item.datetime,
                additional_prop={
                    "thumbnail_b64": thumb_b64,
                    "workflow_metadata": {
                        "stac_collection": stac_collection,
                        "date_start": date_start,
                        "date_end": date_end,
                        "aoi": aoi_polygon,
                    },
                },
                asset_extra_fields={
                    "colormap": {
                        "name": js_cmap,
                        "reversed": cmap_reversed,
                        "min": vmin,
                        "max": vmax,
                        "steps": intervals,
                        "units": index_calculator.units,
                    },
                },
            )
        )
    generate_stac(
        items=output_items,
        output_dir=output_dir,
        title=f"EOPro {index.upper()} calculation",
        description=f"{index.upper()} calculation with {stac_collection}",
    )
