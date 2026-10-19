"""ModelClient backed by a Microsoft Foundry model deployment.

Calls the OpenAI v1 chat completions route of the Foundry resource with an API key.
Docs: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
Settings come from environment variables (names listed in env.example), never from code.
"""

from __future__ import annotations

import os

import httpx

from dugout.agents.pipeline import ModelError, ModelTimeout

ENV_ENDPOINT = "FOUNDRY_ENDPOINT"
ENV_API_KEY = "FOUNDRY_API_KEY"
ENV_MODEL = "FOUNDRY_MODEL"


class FoundryClient:
    def __init__(self, endpoint: str, api_key: str, model: str, *,
                 transport: httpx.BaseTransport | None = None):
        base = endpoint.rstrip("/").removesuffix("/openai/v1")
        self._url = f"{base}/openai/v1/chat/completions"
        self._api_key = api_key
        self._model = model
        self._http = httpx.Client(transport=transport)

    def complete(self, system: str, user: str, *, timeout_s: float) -> str:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._http.post(
                self._url, json=body, headers={"api-key": self._api_key}, timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeout from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            # Status only: the body can echo request details.
            raise ModelError(f"Foundry returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelError("Foundry reply has no message content") from exc
        if not isinstance(content, str):
            raise ModelError("Foundry reply has no message content")
        return content


def client_from_env() -> FoundryClient:
    values = {name: os.environ.get(name, "") for name in (ENV_ENDPOINT, ENV_API_KEY, ENV_MODEL)}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Set {', '.join(missing)} to use the Foundry client (see env.example)")
    return FoundryClient(values[ENV_ENDPOINT], values[ENV_API_KEY], values[ENV_MODEL])
