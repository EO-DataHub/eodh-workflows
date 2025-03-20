from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import click
from pystac_client import Client
from tqdm import tqdm

from src.consts.crs import WGS84
from src.consts.directories import LOCAL_STAC_OUTPUT_DIR
from src.utils.geom import geojson_to_polygon
from src.utils.logging import get_logger
from src.utils.raster import generate_thumbnail_with_continuous_colormap, get_raster_bounds, image_to_base64, save_cog
from src.utils.stac import generate_stac, prepare_stac_asset, prepare_stac_item, prepare_thumbnail_asset
from src.workflows.ds.utils import (
    DATASET_TO_CATALOGUE_LOOKUP,
    DATASET_TO_COLLECTION_LOOKUP,
    prepare_data_array,
    prepare_s2_ard_data_array,
)
from src.workflows.spectral.indices import (
    SPECTRAL_INDICES,
)
from src.workflows.spectral.utils import resolve_rescale_params

if TYPE_CHECKING:
    import pystac

warnings.filterwarnings("ignore", category=UserWarning, message="The argument 'infer_datetime_format'")

_logger = get_logger(__name__)


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
def calculate(  # noqa: PLR0914, RUF100
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

    aoi_polygon: dict[str, Any] = json.loads(aoi)

    sorted_items = query_stac(
        aoi_polygon=aoi_polygon,
        date_end=date_end,
        date_start=date_start,
        stac_collection=stac_collection,
        limit=limit,
    )

    index_calculator = SPECTRAL_INDICES[index]
    output_items = []
    for item in tqdm(sorted_items, desc="Processing items"):
        _logger.info("Working with: %s", item.id)

        # Generate new Item ID to avoid conflicts if running with scatter operator
        item_id = str(uuid4())

        try:
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
        except Exception:
            _logger.exception("Failed to process item: %s - skipping item", item.id)
            continue

        scale, offset = resolve_rescale_params(collection_name=item.collection_id, item_datetime=item.datetime)
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
        mpl_cmap, _ = index_calculator.mpl_colormap
        thumb_fp = output_dir / f"{item_id}_thumb.png"
        generate_thumbnail_with_continuous_colormap(
            index_raster,
            out_fp=thumb_fp,
            colormap=mpl_cmap,
            max_val=vmax,
            min_val=vmin,
        )
        thumb_b64 = image_to_base64(thumb_fp)

        assets = {
            "thumbnail": prepare_thumbnail_asset(thumbnail_path=thumb_fp),
            "data": prepare_stac_asset(
                file_path=raster_path,
                title=index_calculator.full_name,
                asset_extra_fields=index_calculator.asset_extra_fields(index_raster),
            ),
        }

        output_items.append(
            prepare_stac_item(
                id_item=item_id,
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
                assets=assets,
            )
        )
        del raster_arr, index_raster
    generate_stac(
        items=output_items,
        output_dir=output_dir,
        title=f"EOPro {index.upper()} calculation",
        description=f"{index.upper()} calculation with {stac_collection}",
    )


def query_stac(
    aoi_polygon: dict[str, Any],
    date_end: str,
    date_start: str,
    stac_collection: str,
    limit: int | None = None,
    max_cc: float | None = None,
) -> list[pystac.Item]:
    valid_collections = {"sentinel-2-l2a", "sentinel-2-l2a-ard"}
    if stac_collection not in valid_collections:
        msg = (
            f"Unknown STAC collection provided: `{stac_collection}`. "
            f"Available collections: {', '.join(valid_collections)}"
        )
        raise ValueError(msg)

    catalog = Client.open(DATASET_TO_CATALOGUE_LOOKUP[stac_collection])

    filter_spec = {
        "op": "and",
        "args": [
            {"op": "s_intersects", "args": [{"property": "geometry"}, aoi_polygon]},
            {"op": "=", "args": [{"property": "collection"}, DATASET_TO_COLLECTION_LOOKUP[stac_collection]]},
        ],
    }
    if date_start:
        filter_spec["args"].append({"op": ">=", "args": [{"property": "datetime"}, date_start]})  # type: ignore[attr-defined]
    if date_end:
        filter_spec["args"].append({"op": "<=", "args": [{"property": "datetime"}, date_end]})  # type: ignore[attr-defined]
    if max_cc is not None:
        filter_spec["args"].append({"op": "<=", "args": [{"property": "properties.eo:cloud_cover"}, max_cc]})  # type: ignore[attr-defined]

    search = catalog.search(
        collections=[DATASET_TO_COLLECTION_LOOKUP[stac_collection]],
        filter_lang="cql2-json",
        filter=filter_spec,
        max_items=limit,
        fields={
            "include": ["properties.proj:epsg", "properties.proj:code", "properties.eo:cloud_cover"],
        },
    )

    return sorted(search.items(), key=lambda x: x.datetime)
