import json

import httpx
import pytest

from dugout.agents.foundry import FoundryClient, client_from_env
from dugout.agents.pipeline import ModelError, ModelTimeout, NarrationPipeline
from dugout.agents.sample import SAMPLE_PAYLOAD
from dugout.agents.templates import template_narration

ENDPOINT = "https://dugout-test.openai.azure.com"
GOOD = {"headline": "RFC-03 is fading (60%).", "reason": "Changing now: +3.9 pts win probability (strong)."}


def client_with(handler) -> FoundryClient:
    return FoundryClient(ENDPOINT, "test-key", "gpt-5.4-nano", transport=httpx.MockTransport(handler))


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def test_reply_is_returned_and_request_is_well_formed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-key"]
        seen["body"] = json.loads(request.content)
        return reply(json.dumps(GOOD))

    text = client_with(handler).complete("sys", "usr", timeout_s=2.0)
    assert json.loads(text) == GOOD
    assert seen["url"] == f"{ENDPOINT}/openai/v1/chat/completions"
    assert seen["key"] == "test-key"
    body = seen["body"]
    assert body["model"] == "gpt-5.4-nano"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    assert body["response_format"] == {"type": "json_object"}


def test_trailing_slash_and_v1_suffix_in_endpoint_are_tolerated():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return reply("{}")

    for endpoint in (ENDPOINT + "/", ENDPOINT + "/openai/v1/"):
        FoundryClient(endpoint, "k", "m", transport=httpx.MockTransport(handler)).complete("s", "u", timeout_s=1)
    assert urls == [f"{ENDPOINT}/openai/v1/chat/completions"] * 2


def test_timeout_becomes_model_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelTimeout):
        client_with(handler).complete("s", "u", timeout_s=0.5)


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="boom"),
    httpx.Response(429, text="slow down"),
    httpx.Response(200, json={"choices": []}),
    httpx.Response(200, text="not json"),
    httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
])
def test_http_and_shape_errors_become_model_error(response):
    with pytest.raises(ModelError):
        client_with(lambda request: response).complete("s", "u", timeout_s=1)


def test_connection_failure_becomes_model_error():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ModelError):
        client_with(handler).complete("s", "u", timeout_s=1)


def test_error_message_never_contains_the_key():
    with pytest.raises(ModelError) as info:
        client_with(lambda request: httpx.Response(401, text="bad key test-key")).complete("s", "u", timeout_s=1)
    assert "test-key" not in str(info.value)


def test_timeout_is_passed_to_the_transport_layer():
    seen = {}

    def handler(request):
        seen["timeout"] = request.extensions["timeout"]
        return reply("{}")

    client_with(handler).complete("s", "u", timeout_s=1.5)
    assert seen["timeout"]["read"] == 1.5


def test_pipeline_uses_the_reply_when_grounded():
    answers = iter([GOOD, GOOD])
    client = client_with(lambda request: reply(json.dumps(next(answers))))
    card = NarrationPipeline(client).run(SAMPLE_PAYLOAD, "en", "analyst")
    assert card.source == "model"


def test_pipeline_falls_back_to_template_on_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    card = NarrationPipeline(client_with(handler)).run(SAMPLE_PAYLOAD, "en", "analyst")
    expected = template_narration(SAMPLE_PAYLOAD, "en", "analyst")
    assert (card.source, card.fallback, card.headline) == ("template", "timeout", expected.headline)


def test_pipeline_falls_back_to_template_on_error():
    card = NarrationPipeline(client_with(lambda request: httpx.Response(500))).run(SAMPLE_PAYLOAD, "en", "analyst")
    expected = template_narration(SAMPLE_PAYLOAD, "en", "analyst")
    assert (card.source, card.fallback, card.reason) == ("template", "error", expected.reason)


def test_client_from_env_reads_named_variables(monkeypatch):
    monkeypatch.setenv("FOUNDRY_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5.4-nano")
    assert isinstance(client_from_env(), FoundryClient)


@pytest.mark.parametrize("missing", ["FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"])
def test_client_from_env_names_the_missing_variable_only(monkeypatch, missing):
    for name in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"):
        monkeypatch.setenv(name, "secret-value")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError) as info:
        client_from_env()
    assert missing in str(info.value)
    assert "secret-value" not in str(info.value)
