from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
import rioxarray
from shapely.geometry import mapping, shape
from tqdm import tqdm

from src import consts
from src.geom_utils.transform import gejson_to_polygon
from src.raster_utils.save import save_cog_v2
from src.utils.logging import get_logger
from src.workflows.ds.utils import (
    DATASET_TO_COLLECTION_LOOKUP,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pystac import Item

HTTP_OK = 200

EVALSCRIPT_LOOKUP = {
    "clms-corine-lc": consts.sentinel_hub.SH_EVALSCRIPT_CORINELC,
    "clms-water-bodies": consts.sentinel_hub.SH_EVALSCRIPT_WATERBODIES,
}

CLASSES_LOOKUP = {
    "clms-corine-lc": consts.sentinel_hub.SH_CLASSES_DICT_CORINELC,
    "clms-water-bodies": consts.sentinel_hub.SH_CLASSES_DICT_WATERBODIES,
}

_logger = get_logger(__name__)


def _download_sh_item(
    item: Item, item_output_dir: Path, aoi: dict[str, Any], token: str, stac_collection: str, *, timeout: int = 20
) -> Path:
    process_api_url = consts.sentinel_hub.SH_PROCESS_API
    aoi_polygon = gejson_to_polygon(json.dumps(aoi))
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
            item=item, item_output_dir=item_output_dir, aoi=aoi, token=token, stac_collection=stac_collection
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
        with item_path.open("w", encoding="utf-8") as json_file:
            json.dump(item_modified, json_file, indent=4, ensure_ascii=False)
        results.append(item_path)

    return results  # Return the complete dict of results
