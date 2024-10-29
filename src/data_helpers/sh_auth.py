from __future__ import annotations

import os
from typing import TYPE_CHECKING

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from src import consts

if TYPE_CHECKING:
    from requests import Response


def sh_auth_token() -> str:
    client_id = os.environ.get("SH_CLIENT_ID", default=None)
    client_secret = os.environ.get("SH_SECRET", default=None)

    client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=client)

    oauth.register_compliance_hook("access_token_response", _sentinelhub_compliance_hook)

    token = oauth.fetch_token(
        token_url=consts.sentinel_hub.SH_TOKEN_URL,
        client_secret=client_secret,
        include_client_id=True,
    )

    return str(token["access_token"])


def _sentinelhub_compliance_hook(response: Response) -> Response:
    response.raise_for_status()
    return response
