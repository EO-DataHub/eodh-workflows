from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import dask.bag
import dask.config
import geopandas as gpd
import rasterio
import requests
from distributed import Client as DistributedClient, LocalCluster
from rasterio.mask import mask
from shapely.geometry import mapping, shape
from tqdm import tqdm

from src import consts
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pystac import Item

_logger = get_logger(__name__)

N_WORKERS = 10
THREADS_PER_WORKER = 1
DATASET_TO_CATALOGUE_LOOKUP = {
    "sentinel-2-l1c": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/earth-search-aws",
    "sentinel-2-l2a": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/earth-search-aws",
    "sentinel-2-l2a-ard": f"{consts.stac.EODH_CATALOG_API_ENDPOINT}/catalogs/supported-datasets/ceda-stac-catalogue",
    "esa-lccci-glcm": f"{consts.stac.CEDA_CATALOG_API_ENDPOINT}",
    "clms-corine-lc": f"{consts.stac.SH_CATALOG_API_ENDPOINT}",
    "clms-water-bodies": f"{consts.stac.SH_CATALOG_API_ENDPOINT}",
}
DATASET_TO_COLLECTION_LOOKUP = {
    "sentinel-2-l1c": "sentinel-2-l1c",
    "sentinel-2-l2a": "sentinel-2-l2a",
    "sentinel-2-l2a-ard": "sentinel2_ard",
    "esa-lccci-glcm": "land_cover",
    "clms-corine-lc": "byoc-cbdba844-f86d-41dc-95ad-b3f7f12535e9",
    "clms-water-bodies": "byoc-62bf6f6a-c584-48a8-a739-0bc60efee54a",
}


def handle_single_asset_dask(
    asset_id_data_tuple: tuple[str, dict[str, Any]],
    item_output_dir: Path,
    aoi: dict[str, Any],
    *,
    clip: bool = False,
) -> tuple[str, Path]:
    asset_key, asset = asset_id_data_tuple
    asset_url = asset["href"]

    asset_filename = item_output_dir / f"{asset_key}.tif"

    if clip:
        download_and_clip_asset(asset_url, asset_filename, aoi)
    else:
        download_asset(asset_url, asset_filename)

    return asset_key, asset_filename


def download_asset(url: str, output_path: Path, timeout: int = 60) -> None:
    """Download a single asset from a URL."""
    response = requests.get(url, stream=True, timeout=timeout)
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


def get_features_geometry(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Function to parse features from GeoDataFrame in such a manner that rasterio wants them."""
    return [json.loads(gdf.to_json())["features"][0]["geometry"]]


def download_and_clip_asset(url: str, output_path: Path, aoi: dict[str, Any]) -> None:
    """Download and clip a GeoTIFF/COG asset to the AOI without downloading the full asset."""
    _logger.info("Downloading and clipping asset: %s", url)
    # Load AOI geometry
    aoi_geometry = shape(aoi)
    geo = gpd.GeoDataFrame({"geometry": aoi_geometry}, index=[0], crs="EPSG:4326")

    # Use Rasterio to open the remote GeoTIFF
    src: rasterio.io.DatasetReader
    with rasterio.open(url) as src:
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


def download_search_results(
    items: Iterable[Item],
    aoi: dict[str, Any],
    output_dir: Path,
    *,
    clip: bool = False,
) -> list[Path]:
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
            _ = (
                dask.bag.from_sequence(list(item_modified["assets"].items()), partition_size=1)
                .map(handle_single_asset_dask, item_output_dir=item_output_dir, aoi=aoi, clip=clip)
                .compute_from_item()
            )

        # Update hrefs to point to local files
        for asset_tuple in item_modified["assets"].items():
            asset_key, asset = asset_tuple
            asset_filepath = item_output_dir / f"{asset_key}.tif"
            item_modified["assets"][asset_key]["href"] = asset_filepath.as_posix()
            if "role" in item_modified["assets"][asset_key]:
                item_modified["assets"][asset_key]["roles"] = item_modified["assets"][asset_key]["role"]
                item_modified["assets"][asset_key].pop("role")

        # Save JSON definition of the item
        item_path = item_output_dir / f"{item.id}.json"
        with item_path.open("w", encoding="utf-8") as json_file:
            json.dump(item_modified, json_file, indent=4, ensure_ascii=False)
        results.append(item_path)

    return results  # Return the complete dict of results
