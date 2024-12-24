from __future__ import annotations

import json
from io import BytesIO
from typing import TYPE_CHECKING

import requests
import rioxarray
from oauthlib.oauth2 import BackendApplicationClient
from requests import Response
from requests_oauthlib import OAuth2Session

from src import consts
from src.core.settings import current_settings

if TYPE_CHECKING:
    from pystac import Item
    from xarray import DataArray

    from src.workflows.legacy.lulc.helpers import DataSource


EVALSCRIPT_MAPPING = {
    consts.stac.SH_CLMS_CORINELC_LOCAL_NAME: consts.sentinel_hub.SH_EVALSCRIPT_CORINELC,
    consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME: consts.sentinel_hub.SH_EVALSCRIPT_WATERBODIES,
}
HTTP_OK = 200


def sh_get_data(
    token: str,
    source: DataSource,
    bbox: tuple[int | float, int | float, int | float, int | float],
    stac_collection: str,
    item: Item,
    timeout: int = 20,
) -> DataArray:
    process_api_url = consts.sentinel_hub.SH_PROCESS_API

    payload = {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [
                {
                    "type": stac_collection,
                    "dataFilter": {
                        "timeRange": {
                            "from": item.datetime.isoformat(),
                            "to": item.datetime.isoformat(),
                        }
                    },
                }
            ],
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

    response = requests.post(process_api_url, headers=headers, data=json.dumps(payload), timeout=timeout)

    # Checking the response
    if response.status_code == HTTP_OK:
        # Load binary data without saving to disk
        cog_data = BytesIO(response.content)
        data_arr = rioxarray.open_rasterio(cog_data, chunks=consts.compute.CHUNK_SIZE)

        if source.name == consts.stac.SH_CLMS_WATER_BODIES_LOCAL_NAME:
            data_arr = data_arr.rio.write_nodata(consts.sentinel_hub.SH_NODATA_WATERBODIES)

        return data_arr
    error_message = f"Error: {response.status_code}, : {response.text}"
    raise requests.HTTPError(error_message)


def sh_auth_token() -> str:
    settings = current_settings()

    client = BackendApplicationClient(client_id=settings.sh_client_id)
    oauth = OAuth2Session(client=client)

    oauth.register_compliance_hook("access_token_response", _sentinelhub_compliance_hook)

    token = oauth.fetch_token(
        token_url=consts.sentinel_hub.SH_TOKEN_URL,
        client_secret=settings.sh_secret,
        include_client_id=True,
    )

    return str(token["access_token"])


def _sentinelhub_compliance_hook(response: Response) -> Response:
    response.raise_for_status()
    return response
