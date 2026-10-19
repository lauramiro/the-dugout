"""Web PubSub publishing, shared by the decision service and the stub.

Settings (environment): WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB (default "decisions").
Without a connection string there is no publisher and callers skip the push.
"""

from __future__ import annotations

import os
from typing import Protocol


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
