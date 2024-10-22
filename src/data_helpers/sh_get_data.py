from __future__ import annotations

import json
from io import BytesIO
from typing import TYPE_CHECKING

import requests
import rioxarray
from xarray import DataArray

from src import consts

if TYPE_CHECKING:
    from xarray import DataArray

    from src.workflows.lulc.generate_change import DataSource

EVALSCRIPT_MAPPING = {consts.stac.SH_CLMS_CORINELC_LOCAL_NAME: consts.sentinel_hub.SH_EVALSCRIPT_CORINELC}
HTTP_OK = 200


def sh_get_data(
    token: str,
    source: DataSource,
    bbox: tuple[int | float, int | float, int | float, int | float],
    stac_collection: str,
    item_id: str,
) -> DataArray:
    process_api_url = consts.sentinel_hub.SH_PROCESS_API

    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{"type": stac_collection, "dataFilter": {"itemId": item_id}}],
        },
        "evalscript": EVALSCRIPT_MAPPING[source.name],
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

    response = requests.post(process_api_url, headers=headers, data=json.dumps(payload), timeout=20)

    # Checking the response
    if response.status_code == HTTP_OK:
        # Load binary data without saving to disk
        cog_data = BytesIO(response.content)
        return rioxarray.open_rasterio(cog_data, chunks=consts.compute.CHUNK_SIZE)
    error_message = f"Error: {response.status_code}, : {response.text}"
    raise requests.HTTPError(error_message)