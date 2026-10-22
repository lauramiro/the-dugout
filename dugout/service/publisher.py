"""Web PubSub publishing, shared by the decision service and the stub.

Settings (environment): WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB (default "decisions").
Without a connection string there is no publisher and callers skip the push.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

# A dependency sets the root logger to INFO with a stderr handler, which turns on the Azure SDK's
# request logging: about 20 lines per publish, every one of them ingested by Log Analytics. Keep
# the Azure SDK (Web PubSub and Event Hubs) to warnings and errors, in the service and the runner.
logging.getLogger("azure").setLevel(logging.WARNING)


class Publisher(Protocol):
    def publish(self, payload: dict) -> None: ...
    def client_url(self) -> str: ...


class WebPubSubPublisher:
    def __init__(self, connection_string: str, hub: str) -> None:
        from azure.messaging.webpubsubservice import WebPubSubServiceClient

        self._client = WebPubSubServiceClient.from_connection_string(connection_string, hub=hub)

    def publish(self, payload: dict) -> None:
        self._client.send_to_all(message=payload, content_type="application/json")

    def client_url(self) -> str:
        return self._client.get_client_access_token()["url"]


def default_publisher() -> Publisher | None:
    conn = os.environ.get("WEBPUBSUB_CONNECTION_STRING")
    if not conn:
        return None
    return WebPubSubPublisher(conn, os.environ.get("WEBPUBSUB_HUB", "decisions"))
