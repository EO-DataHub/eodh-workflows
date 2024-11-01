from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import click
import rioxarray
import stackstac
from pystac_client import Client
from tqdm import tqdm

from src import consts
from src.consts.crs import WGS84
from src.consts.stac import EVI, INDEX_TO_FULL_NAME_LOOKUP, NDVI, NDWI, SAVI
from src.geom_utils.transform import gejson_to_polygon
from src.local_stac.generate import LOCAL_STAC_OUTPUT_DIR, generate_stac, prepare_stac_item
from src.raster_utils.helpers import get_raster_bounds
from src.raster_utils.save import save_cog
from src.raster_utils.thumbnail import (
    generate_thumbnail_with_continuous_colormap,
    image_to_base64,
)
from src.utils.logging import get_logger
from src.workflows.raster.indices import calculate_index

if TYPE_CHECKING:
    import xarray
    from pystac import Item

warnings.filterwarnings("ignore", category=UserWarning, message="The argument 'infer_datetime_format'")

_logger = get_logger(__name__)
INDEX_TO_CMAP_LOOKUP = {
    NDVI: "RdYlGn",
    NDWI: "RdBu",
    SAVI: "RdYlGn",
    EVI: "YlGn",
}
INDEX_RANGES_LOOKUP = {
    "ndvi": (-1.0, 1.0),
    "ndwi": (-1.0, 1.0),
    "savi": (-1.0, 1.0),
    "evi": (-1.0, 1.0),
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
    type=click.Choice(["NDVI", "NDWI", "EVI", "SAVI"], case_sensitive=False),
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

    if index.lower() not in consts.stac.INDEX_TO_ASSETS_LOOKUP[stac_collection]:
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
            raster_arr = build_raster_array(
                item=item,
                collection=stac_collection,
                index=index,
                bbox=gejson_to_polygon(aoi).bounds,
                epsg=WGS84,
                clip=clip == "True",
            )
            index_raster = calculate_index(index=index, raster_arr=raster_arr)
            raster_path = save_cog(arr=index_raster, item_id=item.id, output_dir=output_dir, epsg=WGS84)
        v_min, v_max = INDEX_RANGES_LOOKUP[index]
        thump_fp = generate_thumbnail_with_continuous_colormap(
            index_raster,
            raster_path=raster_path,
            output_dir=output_dir,
            colormap=INDEX_TO_CMAP_LOOKUP[index],
            max_val=v_max,
            min_val=v_min,
        )
        thumb_b64 = image_to_base64(thump_fp)
        output_items.append(
            prepare_stac_item(
                file_path=raster_path,
                title=INDEX_TO_FULL_NAME_LOOKUP[index],
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
                        "name": INDEX_TO_CMAP_LOOKUP[index],
                        "v_min": v_min,
                        "v_max": v_max,
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


def build_raster_array(
    item: Item,
    collection: str,
    index: str,
    bbox: tuple[int | float, int | float, int | float, int | float],
    epsg: int = WGS84,
    *,
    clip: bool = False,
) -> xarray.DataArray:
    assets_to_use = resolve_assets_for_index(index, collection)
    _logger.info(
        "Building raster array for item '%s' in collection '%s', assets %s will be used",
        item.id,
        collection,
        assets_to_use,
    )
    return (
        (
            stackstac.stack(
                item,
                assets=assets_to_use,
                chunksize=consts.compute.CHUNK_SIZE,
                bounds_latlon=bbox if clip else None,
                epsg=epsg,
            ).assign_coords(band=lambda x: x.common_name.rename("band"))  # use common names
        )
        .squeeze()
        .compute()
    )


def resolve_assets_for_index(index: str, collection: str) -> list[str]:
    return consts.stac.INDEX_TO_ASSETS_LOOKUP[collection][index]
