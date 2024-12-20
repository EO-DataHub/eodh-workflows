from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import dask.bag
import dask.config
import geopandas as gpd
import rasterio
import requests
import rioxarray
from distributed import Client as DistributedClient, LocalCluster
from rasterio.mask import mask
from shapely.geometry import mapping, shape
from tqdm import tqdm

from src import consts
from src.utils.geom import geojson_to_polygon
from src.utils.logging import get_logger
from src.utils.raster import save_cog_v2

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pystac import Item

_logger = get_logger(__name__)

N_WORKERS = 10
THREADS_PER_WORKER = 2
DATASET_TO_CATALOGUE_LOOKUP = {
    "sentinel-2-l1c": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/earth-search-aws",
    "sentinel-2-l2a": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/earth-search-aws",
    "sentinel-2-l2a-ard": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/ceda-stac-catalogue",
    "esa-lccci-glcm": consts.stac.CEDA_CATALOG_API_ENDPOINT,
    "clms-corine-lc": consts.stac.SH_CATALOG_API_ENDPOINT,
    "clms-water-bodies": consts.stac.SH_CATALOG_API_ENDPOINT,
}
DATASET_TO_COLLECTION_LOOKUP = {
    "sentinel-2-l1c": "sentinel-2-l1c",
    "sentinel-2-l2a": "sentinel-2-l2a",
    "sentinel-2-l2a-ard": "sentinel2_ard",
    "esa-lccci-glcm": "land_cover",
    "clms-corine-lc": "byoc-cbdba844-f86d-41dc-95ad-b3f7f12535e9",
    "clms-water-bodies": "byoc-62bf6f6a-c584-48a8-a739-0bc60efee54a",
}

HTTP_OK = 200
EVALSCRIPT_LOOKUP = {
    "clms-corine-lc": consts.sentinel_hub.SH_EVALSCRIPT_CORINELC,
    "clms-water-bodies": consts.sentinel_hub.SH_EVALSCRIPT_WATERBODIES,
}
CLASSES_LOOKUP = {
    "clms-corine-lc": consts.sentinel_hub.SH_CLASSES_DICT_CORINELC,
    "clms-water-bodies": consts.sentinel_hub.SH_CLASSES_DICT_WATERBODIES,
}


def handle_single_asset_dask(
    asset_id_data_tuple: tuple[str, dict[str, Any]],
    item_output_dir: Path,
    aoi: dict[str, Any],
    *,
    clip: bool = False,
) -> tuple[str, dict[str, Any]]:
    asset_key, asset = asset_id_data_tuple
    asset_filename = item_output_dir / f"{asset_key}.tif"
    asset = download_and_clip_asset(asset, asset_filename, aoi) if clip else download_asset(asset, asset_filename)
    return asset_key, asset


def download_asset(asset: dict[str, Any], output_path: Path, timeout: int = 60) -> dict[str, Any]:
    """Download a single asset from a URL."""
    response = requests.get(asset["href"], stream=True, timeout=timeout)
    response.raise_for_status()  # Raise an error for bad status codes
    total_size = int(response.headers.get("content-length", 0))
    with output_path.open("wb") as f, tqdm(
        desc=f"Downloading {output_path.name}",
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as progress:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                progress.update(len(chunk))
    asset["href"] = output_path.as_posix()
    return asset


def get_features_geometry(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Function to parse features from GeoDataFrame in such a manner that rasterio wants them."""
    return [json.loads(gdf.to_json())["features"][0]["geometry"]]


def download_and_clip_asset(asset: dict[str, Any], output_path: Path, aoi: dict[str, Any]) -> dict[str, Any]:
    """Download and clip a GeoTIFF/COG asset to the AOI without downloading the full asset."""
    _logger.info("Downloading and clipping asset: %s", asset["href"])
    # Load AOI geometry
    aoi_geometry = shape(aoi)
    geo = gpd.GeoDataFrame({"geometry": aoi_geometry}, index=[0], crs="EPSG:4326")

    # Use Rasterio to open the remote GeoTIFF
    src: rasterio.io.DatasetReader
    with rasterio.open(asset["href"]) as src:
        geo = geo.to_crs(src.crs)
        aoi_geom = get_features_geometry(geo)
        data, out_transform = mask(dataset=src, shapes=aoi_geom, all_touched=True, crop=True)
        out_meta = src.meta.copy()

    # Update metadata
    out_meta.update({
        "driver": "GTiff",
        "height": data.shape[-2],
        "width": data.shape[-1],
        "transform": out_transform,
        "crs": src.crs,
    })

    # Save clipped raster
    dest: rasterio.io.DatasetWriter
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(data)

    asset["href"] = output_path.as_posix()
    asset["proj:shape"] = data.squeeze().shape
    asset["proj:transform"] = out_transform
    asset["proj:epsg"] = src.crs.to_epsg()

    return asset


def download_search_results(
    items: Iterable[Item],
    aoi: dict[str, Any],
    output_dir: Path,
    asset_rename: dict[str, str] | None = None,
    *,
    clip: bool = False,
) -> list[Path]:
    asset_rename = asset_rename or {}
    results = []  # Initialize a list to collect results
    progress_bar = tqdm(sorted(items, key=lambda x: x.datetime), desc="Processing items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        item_output_dir = output_dir / "source_data" / item.id
        item_output_dir.mkdir(parents=True, exist_ok=True)

        item_modified = item.to_dict()

        # Adjust geometry and bbox if clipping
        new_geometry = shape(item.geometry)
        if clip:
            # Update geometry and bbox to reflect clipped area
            new_geometry = new_geometry.intersection(shape(aoi))
            item_modified["geometry"] = mapping(new_geometry)
            item_modified["bbox"] = new_geometry.bounds

        # Filter non-raster items
        for asset_key, asset in item.assets.items():
            media_type = asset.media_type or Path(asset.href).suffix.replace(".", "")
            if media_type.lower() not in {
                "image/tiff; application=geotiff; profile=cloud-optimized",
                "tif",
                "tiff",
                "geotiff",
                "cog",
            }:
                item_modified["assets"].pop(asset_key)
                continue

        # Download assets in parallel using dask
        dask.config.set({"distributed.comm.timeouts.tcp": "30s"})
        with LocalCluster(n_workers=N_WORKERS, threads_per_worker=THREADS_PER_WORKER) as cluster, DistributedClient(
            cluster
        ):
            assets_records: list[tuple[str, dict[str, Any]]] = (
                dask.bag.from_sequence(list(item_modified["assets"].items()), partition_size=1)
                .map(handle_single_asset_dask, item_output_dir=item_output_dir, aoi=aoi, clip=clip)
                .compute()
            )

        # Replace assets
        for asset_key, asset in assets_records:
            item_modified["assets"].pop(asset_key)
            item_modified["assets"][asset_rename.get(asset_key, asset_key)] = asset

        # Save JSON definition of the item
        item_path = item_output_dir / f"{item.id}.json"
        item_path.write_text(json.dumps(item_modified, indent=4), encoding="utf-8")
        results.append(item_path)

    return results  # Return the complete dict of results


def _download_sh_item(
    item: Item, item_output_dir: Path, aoi: dict[str, Any], token: str, stac_collection: str, *, timeout: int = 20
) -> Path:
    process_api_url = consts.sentinel_hub.SH_PROCESS_API
    aoi_polygon = geojson_to_polygon(json.dumps(aoi))
    bbox = aoi_polygon.bounds

    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [
                {
                    "type": DATASET_TO_COLLECTION_LOOKUP[stac_collection],
                    "dataFilter": {
                        "timeRange": {
                            "from": item.datetime.isoformat(),
                            "to": item.datetime.isoformat(),
                        }
                    },
                }
            ],
        },
        "evalscript": EVALSCRIPT_LOOKUP[stac_collection],
        "output": {
            "responses": [
                {
                    "identifier": "default",
                    "format": {"type": "image/tiff", "parameters": {"compression": "LZW", "cog": True}},
                }
            ]
        },
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.post(process_api_url, headers=headers, data=json.dumps(payload), timeout=timeout)

    # Checking the response
    if response.status_code == HTTP_OK:
        # Load binary data without saving to disk
        cog_data = BytesIO(response.content)
        data_arr = rioxarray.open_rasterio(cog_data, chunks=consts.compute.CHUNK_SIZE)

        if data_arr.rio.nodata is None:
            data_arr.rio.write_nodata(0, inplace=True)

        return save_cog_v2(arr=data_arr, output_file_path=item_output_dir / "data.tif")
    error_message = f"Error: {response.status_code}, : {response.text}"
    raise requests.HTTPError(error_message)


def download_sentinel_hub(
    items: Iterable[Item],
    aoi: dict[str, Any],
    output_dir: Path,
    token: str,
    stac_collection: str,
    *,
    clip: bool = False,
) -> list[Path]:
    results = []  # Initialize a list to collect results
    progress_bar = tqdm(sorted(items, key=lambda x: x.datetime), desc="Downloading items")
    for item in progress_bar:
        progress_bar.set_description(f"Working with: {item.id}")

        item_output_dir = output_dir / "source_data" / item.id
        item_output_dir.mkdir(parents=True, exist_ok=True)

        item_modified = item.to_dict()

        # Adjust geometry and bbox if clipping
        new_geometry = shape(item.geometry)
        if clip:
            # Update geometry and bbox to reflect clipped area
            new_geometry = new_geometry.intersection(shape(aoi))
            item_modified["geometry"] = mapping(new_geometry)
            item_modified["bbox"] = new_geometry.bounds

        # Filter non-raster items
        for asset_key, asset in item.assets.items():
            media_type = asset.media_type or Path(asset.href).suffix.replace(".", "")
            if media_type.lower() not in {
                "image/tiff; application=geotiff; profile=cloud-optimized",
                "tif",
                "tiff",
                "geotiff",
                "cog",
            }:
                item_modified["assets"].pop(asset_key)
                continue

        # Download assets in parallel using dask
        downloaded_path = _download_sh_item(
            item=item,
            item_output_dir=item_output_dir,
            aoi=aoi,
            token=token,
            stac_collection=stac_collection,
        )

        # STAC in SentinelHub has no assets
        item_modified["assets"]["data"] = {
            "href": downloaded_path.as_posix(),
            "title": f"Data for {stac_collection}",
            "roles": ["data"],
            "classification:classes": CLASSES_LOOKUP[stac_collection],
        }

        # Adjust other STAC item properties
        item_modified["properties"]["proj:epsg"] = consts.crs.WGS84
        item_modified["properties"].pop("proj:bbox", None)
        item_modified["properties"].pop("proj:geometry", None)

        # Save JSON definition of the item
        item_path = item_output_dir / f"{item.id}.json"
        item_path.write_text(json.dumps(item_modified, indent=4, ensure_ascii=False), encoding="utf-8")
        results.append(item_path)

    return results  # Return the complete dict of results
