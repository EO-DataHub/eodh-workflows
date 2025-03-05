from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import dask.bag
import dask.config
import geopandas as gpd
import pystac
import rasterio
import requests
import rioxarray
import stackstac
import xarray
from distributed import Client as DistributedClient, LocalCluster
from pystac import Item
from rasterio.mask import mask
from retry import retry
from shapely.geometry import mapping, shape
from tqdm import tqdm

from src import consts
from src.consts.stac import LOCAL_COLLECTION_NAME, SENTINEL_2_ARD_COLLECTION_NAME, SENTINEL_2_L2A_COLLECTION_NAME
from src.core.settings import current_settings
from src.utils.geom import geojson_to_polygon
from src.utils.logging import get_logger
from src.utils.raster import save_cog_v2
from src.utils.stac import prepare_stac_asset

if TYPE_CHECKING:
    from collections.abc import Iterable


_logger = get_logger(__name__)
settings = current_settings()

N_WORKERS = 10
THREADS_PER_WORKER = 2
DATASET_TO_CATALOGUE_LOOKUP = {
    "sentinel-2-l1c": f"{settings.eodh.stac_api_endpoint}/catalogs/supported-datasets/catalogs/earth-search-aws",
    "sentinel-2-l2a": f"{settings.eodh.stac_api_endpoint}/catalogs/supported-datasets/catalogs/earth-search-aws",
    "sentinel-2-l2a-ard": f"{settings.eodh.stac_api_endpoint}/catalogs/supported-datasets/catalogs/ceda-stac-catalogue",
    "esa-lccci-glcm": f"{settings.eodh.stac_api_endpoint}/catalogs/supported-datasets/catalogs/ceda-stac-catalogue",
    "clms-corine-lc": settings.sentinel_hub.stac_api_endpoint,
    "clms-water-bodies": settings.sentinel_hub.stac_api_endpoint,
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


@retry(tries=3, delay=3, backoff=2)
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


@retry(tries=3, delay=3, backoff=2)
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


@retry(tries=3, delay=3, backoff=2)
def _download_sh_item(
    item: Item,
    item_output_dir: Path,
    aoi: dict[str, Any],
    token: str,
    stac_collection: str,
    *,
    timeout: int = 20,
) -> Path:
    process_api_url = settings.sentinel_hub.process_api_endpoint
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


@retry(tries=3, delay=3, backoff=2)
def split_s2_ard_cogs_into_separate_assets(fps: Iterable[Path]) -> None:
    for fp in fps:
        item = Item.from_file(fp)
        cog_asset = item.assets.pop("cog")
        cog_fp = Path(cog_asset.href)
        arr = rioxarray.open_rasterio(cog_fp)

        for band, new_band_name in zip(
            arr.band,
            ["blue", "green", "red", "rededge1", "rededge2", "rededge3", "nir", "nir08", "swir16", "swir22"],
        ):
            new_asset_fp = cog_fp.parent / f"{new_band_name}.tif"
            band_arr = arr.sel(band=band)
            band_arr.rio.to_raster(new_asset_fp)
            item.add_asset(
                key=new_band_name,
                asset=prepare_stac_asset(
                    file_path=new_asset_fp,
                    title=cog_asset.title,
                    description=cog_asset.description,
                    asset_extra_fields={
                        "proj:shape": band_arr.shape,
                        "proj:transform": band_arr.rio.transform(),
                        "proj:epsg": band_arr.rio.crs.to_epsg(),
                    },
                ),
            )
            fp.write_text(json.dumps(item.to_dict(), indent=4, ensure_ascii=False), encoding="utf-8")
        cog_fp.unlink()


@retry(tries=3, delay=3, backoff=2)
def prepare_data_array(
    item: pystac.Item,
    assets: list[str],
    bbox: tuple[float, float, float, float] | None = None,
) -> xarray.DataArray:
    mapped_asset_ids = unify_asset_identifiers(assets_to_use=assets, collection=item.collection_id)

    epsg: int | None = None
    if not all(item.assets[a].extra_fields.get("proj:epsg", None) for a in assets):
        epsg = item.properties.get("proj:epsg", None)

    return (
        stackstac.stack(
            [item],
            assets=assets,
            chunksize=consts.compute.CHUNK_SIZE,
            bounds_latlon=bbox,
            epsg=epsg,
        )
        .assign_coords({"band": mapped_asset_ids})  # use common names
        .squeeze()
        .compute()
    )


def prepare_s2_ard_data_array(
    item: pystac.Item,
    aoi: dict[str, Any] | None = None,
) -> xarray.DataArray:
    if aoi is None:
        return _prepare_s2_ard_data_array_no_clip(item)
    cog = _prepare_s2_ard_data_array_clip(
        item,
        aoi=aoi,
        asset_name="cog",
        assign_coords={
            "band": [
                "blue",
                "green",
                "red",
                "rededge1",
                "rededge2",
                "rededge3",
                "nir",
                "nir08",
                "swir16",
                "swir22",
            ]
        },
    )
    cloud = _prepare_s2_ard_data_array_clip(
        item,
        aoi=aoi,
        asset_name="cloud",
        assign_coords={"band": ["cloud"]},
    )
    return xarray.concat([cog, cloud], dim="band")


@retry(tries=3, delay=3, backoff=2)
def _prepare_s2_ard_data_array_clip(
    item: pystac.Item,
    aoi: dict[str, Any],
    asset_name: str,
    assign_coords: dict[str, list[str]],
) -> xarray.DataArray:
    # Load AOI geometry
    aoi_geometry = shape(aoi)
    geo = gpd.GeoDataFrame({"geometry": aoi_geometry}, index=[0], crs="EPSG:4326")
    asset = item.assets[asset_name]

    # Use Rasterio to open the remote GeoTIFF
    src: rasterio.io.DatasetReader
    with rasterio.open(asset.href) as src:
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
    with tempfile.TemporaryDirectory() as tmpdir_name:
        dest: rasterio.io.DatasetWriter
        with rasterio.open(Path(tmpdir_name) / f"{asset_name}.tif", "w", **out_meta) as dest:
            dest.write(data)
        return (
            rioxarray.open_rasterio(Path(tmpdir_name) / f"{asset_name}.tif")
            .compute()
            .assign_coords(assign_coords)
            .rio.reproject("EPSG:4326")
        )


@retry(tries=3, delay=3, backoff=2)
def _prepare_s2_ard_data_array_no_clip(item: pystac.Item) -> xarray.DataArray:
    cog_asset = item.assets["cog"]
    cloud_asset = item.assets["cloud"]
    with tempfile.TemporaryDirectory() as tmpdir_name:
        download_asset(asset=cog_asset.to_dict(), output_path=Path(tmpdir_name) / "cog.tif")
        download_asset(asset=cloud_asset.to_dict(), output_path=Path(tmpdir_name) / "cloud.tif")
        arr = (
            rioxarray.open_rasterio(Path(tmpdir_name) / "cog.tif")
            .compute()
            .assign_coords({
                "band": [
                    "blue",
                    "green",
                    "red",
                    "rededge1",
                    "rededge2",
                    "rededge3",
                    "nir",
                    "nir08",
                    "swir16",
                    "swir22",
                ]
            })
            .rio.reproject("EPSG:4326")
        )
        clouds_arr = (
            rioxarray.open_rasterio(Path(tmpdir_name) / "cloud.tif")
            .compute()
            .assign_coords({"band": ["cloud"]})
            .rio.reproject("EPSG:4326")
        )
        return xarray.concat((arr, clouds_arr), dim="band")


def unify_asset_identifiers(assets_to_use: list[str], collection: str) -> list[str]:
    if collection in {SENTINEL_2_L2A_COLLECTION_NAME, LOCAL_COLLECTION_NAME, SENTINEL_2_ARD_COLLECTION_NAME}:
        return assets_to_use

    msg = f"Unknown collection: {collection}. Cannot resolve asset identifiers to use."
    raise ValueError(msg)
