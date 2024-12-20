from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import click
import pystac
from pystac_client import Client
from shapely.geometry import mapping

from src.consts.directories import LOCAL_DATA_DIR
from src.utils.geom import geojson_to_polygon
from src.utils.logging import get_logger
from src.utils.sentinel_hub import sh_auth_token
from src.utils.stac import prepare_local_stac
from src.workflows.ds.utils import (
    DATASET_TO_CATALOGUE_LOOKUP,
    DATASET_TO_COLLECTION_LOOKUP,
    download_search_results,
    download_sentinel_hub,
    split_s2_ard_cogs_into_separate_assets,
)

_logger = get_logger(__name__)


@click.command(help="Query Specified STAC Collection")
@click.option(
    "--stac_collection",
    required=True,
    help="The name of the STAC collection to get the data from",
)
@click.option(
    "--area",
    required=True,
    help="Area of Interest as GeoJSON",
)
@click.option(
    "--date_start",
    required=True,
    help="Start date for the STAC query",
)
@click.option(
    "--date_end",
    help="End date for the STAC query - will use current UTC date if not specified",
)
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
    default="True",
    type=click.Choice(["True", "False"], case_sensitive=False),
    help="A flag indicating whether to crop the data to the AOI",
)
@click.option(
    "--output_dir",
    type=click.Path(path_type=Path, resolve_path=True),  # type: ignore[type-var]
    help="Path to the output directory - will create new dir in CWD/data/stac-catalog if not provided",
)
@click.option(
    "--orbit_direction",
    required=False,
    type=click.Choice(["Ascending", "Descending"], case_sensitive=False),
    help="Orbit direction options",
)
@click.option(
    "--polarization",
    required=False,
    type=click.Choice(["VV", "VV+VH", "HH", "HH+HV"], case_sensitive=False),
    help="Polarization options",
)
@click.option(
    "--cloud_cover_min",
    required=False,
    type=click.INT,
    help="Min cloud cover",
)
@click.option(
    "--cloud_cover_max",
    required=False,
    type=click.INT,
    help="Max cloud cover",
)
def query(
    stac_collection: str,
    area: str,
    date_start: str,
    date_end: str,
    limit: int = 50,
    clip: Literal["True", "False"] = "False",
    polarization: str | None = None,
    orbit_direction: str | None = None,
    cloud_cover_min: int | None = None,
    cloud_cover_max: int | None = None,
    output_dir: Path | None = None,
) -> None:
    aoi = json.loads(area)
    _logger.info(
        "Running with:\n%s",
        json.dumps(
            {
                "stac_collection": stac_collection,
                "area": area,
                "date_start": date_start,
                "date_end": date_end,
                "limit": limit,
                "clip": clip,
                "polarization": polarization,
                "orbit_direction": orbit_direction,
                "cloud_cover_min": cloud_cover_min,
                "cloud_cover_max": cloud_cover_max,
                "output_dir": output_dir.as_posix() if output_dir is not None else None,
            },
            indent=4,
        ),
    )

    output_dir = output_dir or LOCAL_DATA_DIR / "ds-query"
    output_dir.mkdir(exist_ok=True, parents=True)

    if stac_collection == "sentinel-1-grd":
        handle_s1_query(
            stac_collection=stac_collection,
            aoi=aoi,
            date_start=date_start,
            date_end=date_end,
            limit=limit,
            clip=clip,
            polarization=polarization,
            orbit_direction=orbit_direction,
        )

    elif stac_collection in {"sentinel-2-l2a", "sentinel-2-l2a-ard"}:
        handle_s2_query(
            stac_collection=stac_collection,
            aoi=aoi,
            date_start=date_start,
            date_end=date_end,
            limit=limit,
            clip=clip,
            cloud_cover_max=cloud_cover_max,
            cloud_cover_min=cloud_cover_min,
            output_dir=output_dir,
        )

    elif stac_collection in {"clms-corine-lc", "clms-water-bodies"}:
        handle_sh_query(
            stac_collection=stac_collection,
            aoi=aoi,
            date_start=date_start,
            date_end=date_end,
            clip=clip,
            limit=limit,
            output_dir=output_dir,
        )

    elif stac_collection == "esa-lccci-glcm":
        handle_esa_cci_glc_query(
            aoi=aoi,
            date_start=date_start,
            date_end=date_end,
            clip=clip,
            limit=limit,
            output_dir=output_dir,
        )

    else:
        msg = f"Unsupported stac collection: {stac_collection!r}"
        raise ValueError(msg)


def handle_s1_query(
    stac_collection: str,
    aoi: dict[str, Any],
    date_start: str,
    date_end: str,
    limit: int = 50,
    clip: Literal["True", "False"] = "False",
    polarization: str | None = None,
    orbit_direction: str | None = None,
    output_dir: Path | None = None,
) -> None:
    raise NotImplementedError


def handle_s2_query(
    stac_collection: str,
    aoi: dict[str, Any],
    date_start: str,
    date_end: str,
    output_dir: Path,
    limit: int = 50,
    clip: Literal["True", "False"] = "False",
    cloud_cover_min: int | None = None,
    cloud_cover_max: int | None = None,
) -> None:
    # Ensure output directory is set
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect to STAC API
    catalog = Client.open(DATASET_TO_CATALOGUE_LOOKUP[stac_collection])
    stac_collection = DATASET_TO_COLLECTION_LOOKUP[stac_collection]

    # Define your search with CQL2 syntax
    filter_spec = {
        "op": "and",
        "args": [
            {"op": "s_intersects", "args": [{"property": "geometry"}, aoi]},
            {"op": "=", "args": [{"property": "collection"}, stac_collection]},
        ],
    }
    if date_start:
        filter_spec["args"].append({"op": ">=", "args": [{"property": "datetime"}, date_start]})  # type: ignore[attr-defined]
    if date_end:
        filter_spec["args"].append({"op": "<=", "args": [{"property": "datetime"}, date_end]})  # type: ignore[attr-defined]
    if cloud_cover_min is not None:
        filter_spec["args"].append({"op": ">=", "args": [{"property": "properties.eo:cloud_cover"}, cloud_cover_min]})  # type: ignore[attr-defined]
    if cloud_cover_max is not None:
        filter_spec["args"].append({"op": "<=", "args": [{"property": "properties.eo:cloud_cover"}, cloud_cover_max]})  # type: ignore[attr-defined]

    search = catalog.search(
        collections=[stac_collection],
        filter_lang="cql2-json",
        filter=filter_spec,
        max_items=limit,
        fields={
            "include": ["properties.proj:epsg"],
        },
    )

    downloaded = download_search_results(
        items=search.items(),
        aoi=aoi,
        output_dir=output_dir,
        clip=clip == "True",
    )

    if stac_collection == "sentinel2_ard":
        split_s2_ard_cogs_into_separate_assets(downloaded)

    new_catalog = prepare_local_stac(
        items_paths=downloaded,
        title=f"Downloaded {stac_collection}",
        description=f"Query for {date_start} - {date_end}",
    )

    new_catalog.normalize_hrefs(output_dir.as_posix())
    new_catalog.make_all_asset_hrefs_relative()
    new_catalog.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def handle_esa_cci_glc_query(
    aoi: dict[str, Any],
    date_start: str,
    date_end: str,
    limit: int = 50,
    clip: Literal["True", "False"] = "True",
    output_dir: Path | None = None,
) -> None:
    # Ensure output directory is set
    if output_dir is None:
        output_dir = Path("./stac_downloads")
    output_dir.mkdir(parents=True, exist_ok=True)

    aoi_polygon = geojson_to_polygon(json.dumps(aoi))

    catalog = Client.open(DATASET_TO_CATALOGUE_LOOKUP["esa-lccci-glcm"])
    search = catalog.search(
        collections=[DATASET_TO_COLLECTION_LOOKUP["esa-lccci-glcm"]],
        datetime=f"{date_start}/{date_end}",
        intersects=mapping(aoi_polygon),
        max_items=limit,
    )

    if clip == "False":
        _logger.warning("Argument clip=False is not supported, data will be clipped to provided aoi.")

    downloaded = download_search_results(
        items=search.items(),
        aoi=aoi,
        output_dir=output_dir,
        asset_rename={"GeoTIFF": "data"},
        clip=True,
    )

    new_catalog = prepare_local_stac(
        items_paths=downloaded,
        title="Downloaded esa-lccci-glcm",
        description=f"Query for {date_start} - {date_end}",
    )

    new_catalog.normalize_hrefs(output_dir.as_posix())
    new_catalog.make_all_asset_hrefs_relative()
    new_catalog.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)


def handle_sh_query(
    stac_collection: str,
    aoi: dict[str, Any],
    date_start: str,
    date_end: str,
    limit: int = 50,
    clip: Literal["True", "False"] = "False",
    output_dir: Path | None = None,
) -> None:
    # Ensure output directory is set
    if output_dir is None:
        output_dir = Path("./stac_downloads")
    output_dir.mkdir(parents=True, exist_ok=True)

    aoi_polygon = geojson_to_polygon(json.dumps(aoi))

    # Sentinel Hub requires authentication
    token = sh_auth_token()

    catalog = Client.open(DATASET_TO_CATALOGUE_LOOKUP[stac_collection], headers={"Authorization": f"Bearer {token}"})
    search = catalog.search(
        collections=[DATASET_TO_COLLECTION_LOOKUP[stac_collection]],
        datetime=f"{date_start}/{date_end}",
        intersects=mapping(aoi_polygon),
        max_items=limit,
    )

    if clip == "False":
        _logger.warning("Argument clip=False is not supported, data will be clipped to provided aoi.")

    downloaded = download_sentinel_hub(
        items=search.items(),
        aoi=aoi,
        output_dir=output_dir,
        token=token,
        stac_collection=stac_collection,
        clip=True,
    )

    new_catalog = prepare_local_stac(
        items_paths=downloaded,
        title=f"Downloaded {stac_collection}",
        description=f"Query for {date_start} - {date_end}",
    )

    new_catalog.normalize_hrefs(output_dir.as_posix())
    new_catalog.make_all_asset_hrefs_relative()
    new_catalog.normalize_and_save(output_dir.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)
