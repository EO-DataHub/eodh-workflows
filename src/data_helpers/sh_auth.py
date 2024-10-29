from __future__ import annotations

from typing import TYPE_CHECKING

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from src import consts
from src.core.settings import current_settings

if TYPE_CHECKING:
    from requests import Response


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
