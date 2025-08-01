from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import click
import numpy as np
from pystac import Item
from pystac_client import Client
from requests import HTTPError
from shapely.geometry import Polygon, mapping
from tqdm import tqdm

from eodh_workflows.consts.crs import WGS84
from eodh_workflows.consts.directories import LOCAL_STAC_OUTPUT_DIR
from eodh_workflows.core.settings import current_settings
from eodh_workflows.utils.geom import calculate_geodesic_area, geojson_to_polygon
from eodh_workflows.utils.logging import get_logger
from eodh_workflows.utils.raster import (
    build_raster_array,
    generate_thumbnail_with_discrete_classes,
    get_raster_bounds,
    image_to_base64,
    save_cog,
)
from eodh_workflows.utils.sentinel_hub import sh_auth_token
from eodh_workflows.utils.stac import generate_stac, prepare_stac_asset, prepare_stac_item, prepare_thumbnail_asset
from eodh_workflows.workflows.legacy.lulc.helpers import (
    DATASOURCE_LOOKUP,
    DataSource,
    get_classes,
    get_classes_orig_dict,
)

if TYPE_CHECKING:
    import xarray
    from pystac import Item

_logger = get_logger(__name__)
settings = current_settings()


@click.command(help="Generate LULC change")
@click.option(
    "--source",
    type=click.Choice(DATASOURCE_LOOKUP.keys(), case_sensitive=True),
    required=True,
    help="Source dataset to use",
)
@click.option("--aoi", required=True, help="The area of interest as GeoJSON in EPSG:4326")
@click.option("--date_start", required=True, help="Start date in ISO 8601 used to search input data")
@click.option("--date_end", required=True, help="End date in ISO 8601 used to search input data")
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD if not provided",
)
def generate_lulc_change(  # noqa: PLR0914, RUF100
    source: str,
    aoi: str,
    date_start: str,
    date_end: str,
    output_dir: Path | None = None,
) -> None:
    initial_arguments = {"source": source, "aoi": aoi, "date_start": date_start, "date_end": date_end}
    _logger.info(
        "Running with:\n%s",
        json.dumps(initial_arguments, indent=4),
    )
    output_dir = output_dir or LOCAL_STAC_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True, parents=True)

    source_ds: DataSource = DATASOURCE_LOOKUP[source]

    # Transferring the AOI
    aoi_polygon = geojson_to_polygon(aoi)

    items = _get_data(source_ds, aoi_polygon, date_start, date_end)

    if not items:
        _logger.warning("No items found using specified criteria.")
        return

    classes_orig_dict = get_classes_orig_dict(source_ds, items[0])
    classes_unique_values = get_classes(classes_orig_dict)

    # Calculating lulc change
    stac_items: list[Item] = []

    progress_bar = tqdm(items, desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        # Generate new Item ID to avoid conflicts if running with scatter operator
        item_id = str(uuid4())

        # Build array
        try:
            raster_arr = build_raster_array(source=source_ds, item=item, bbox=aoi_polygon.bounds)
        except HTTPError:
            _logger.exception("Failed to build raster array. Skipping item: %s", item.id)
            continue

        bounds_polygon = get_raster_bounds(raster_arr)
        area_m2 = calculate_geodesic_area(bounds_polygon)

        # Count occurrences for each class
        classes_shares: dict[str, float] = _get_shares_for_classes(raster_arr, classes_unique_values)
        raster_arr.attrs["lulc_classes_percentage"] = classes_shares

        classes_m2: dict[str, float] = _get_m2_for_classes(classes_shares, area_m2)
        raster_arr.attrs["lulc_classes_m2"] = classes_m2

        # Save COG with lulc change values in metadata
        raster_path = save_cog(arr=raster_arr, asset_id=f"{item_id}_classification", epsg=WGS84, output_dir=output_dir)
        thumb_fp = output_dir / f"{item_id}_thumb.png"
        generate_thumbnail_with_discrete_classes(
            raster_arr,
            out_fp=thumb_fp,
            classes_list=classes_orig_dict,
        )
        thumb_b64 = image_to_base64(thumb_fp)

        assets = {
            "thumbnail": prepare_thumbnail_asset(thumb_fp),
            "data": prepare_stac_asset(
                title=DATASOURCE_LOOKUP[source].name,
                file_path=raster_path,
                asset_extra_fields={
                    "classification:classes": classes_orig_dict,
                },
            ),
        }

        # Create STAC definition for each item processed
        # Include lulc change in STAC item properties
        stac_items.append(
            prepare_stac_item(
                id_item=item_id,
                geometry=bounds_polygon,
                epsg=raster_arr.rio.crs.to_epsg(),
                transform=list(raster_arr.rio.transform()),
                datetime=item.datetime,
                additional_prop={
                    "lulc_classes_percentage": classes_shares,
                    "lulc_classes_m2": classes_m2,
                    "thumbnail_b64": thumb_b64,
                    "workflow_metadata": {
                        "stac_collection": source,
                        "date_start": date_start,
                        "date_end": date_end,
                        "aoi": mapping(aoi_polygon),
                    },
                },
                assets=assets,
            )
        )

    # Generate local STAC for processed data
    generate_stac(
        items=stac_items,
        output_dir=output_dir,
        title="EOPro Land Cover Change Detection",
        description=f"Land Cover Change Detection using {source} dataset",
    )


def _get_data(source: DataSource, aoi_polygon: Polygon, date_start: str, date_end: str) -> list[Item]:
    catalog = Client.open(
        source.catalog,
        headers={"Authorization": f"Bearer {sh_auth_token()}"}
        if source.catalog == settings.sentinel_hub.stac_api_endpoint
        else None,
    )

    search = catalog.search(
        collections=[source.collection],
        datetime=f"{date_start}/{date_end}",
        intersects=mapping(aoi_polygon),
        fields={
            "include": ["properties.geospatial_lon_resolution", "properties.geospatial_lat_resolution"],
            "exclude": [],
        }
        if source.catalog != settings.sentinel_hub.stac_api_endpoint
        else None,
    )

    return sorted(search.items(), key=lambda item: item.datetime)


def _get_m2_for_classes(percentage_dict: dict[str, float], full_area_m2: float) -> dict[str, float]:
    return {key: (value / 100) * full_area_m2 for key, value in percentage_dict.items()}


def _get_shares_for_classes(input_data: xarray.DataArray, unique_values: set[int]) -> dict[str, float]:
    data = input_data.to_numpy()
    unique_values_for_array, counts = np.unique(data, return_counts=True)

    counts_dict = {
        str(int(value)): float(count / data.size) * 100
        for value, count in zip(unique_values_for_array, counts, strict=False)
    }

    missing_values = unique_values.difference(set(unique_values_for_array))
    counts_dict.update({str(value): 0.0 for value in missing_values})

    return counts_dict
