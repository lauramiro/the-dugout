"""Card service: engine payload plus pipeline narration, cached per (decision_id, locale, mode)."""
import pytest

from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.agents.sample import SAMPLE_PAYLOAD
from dugout.service.cards import CardService
from dugout.service.store import MemoryStore

SNAPSHOT = {"t_ms": 3_720_000, "score": {"RFC": 1, "CAS": 0}}


class CountingEngine:
    def __init__(self):
        self.calls = []

    def __call__(self, snapshot, team, trigger):
        self.calls.append((team, trigger))
        return {**SAMPLE_PAYLOAD, "team": team, "trigger": trigger}


class CountingPipeline:
    def __init__(self):
        self.inner = NarrationPipeline(StubClient())
        self.calls = []

    def run(self, payload, locale="en", mode="casual"):
        self.calls.append((payload["decision_id"], locale, mode))
        return self.inner.run(payload, locale, mode)


@pytest.fixture
def parts():
    engine, pipeline = CountingEngine(), CountingPipeline()
    return engine, pipeline, CardService(engine, pipeline, MemoryStore())


def test_open_runs_the_engine_once_and_stores_the_payload(parts):
    engine, _, svc = parts
    payload = svc.open(SNAPSHOT, "RFC", "condition_drop")
    assert payload["decision_id"] == "rfc-62-01"
    assert engine.calls == [("RFC", "condition_drop")]
    assert svc.payload("rfc-62-01") == payload


def test_card_carries_engine_numbers_and_narration(parts):
    _, _, svc = parts
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    card = svc.card("rfc-62-01", "es", "analyst")
    assert card["decision_id"] == "rfc-62-01"
    assert card["locale"] == "es" and card["mode"] == "analyst"
    assert card["payload"] == SAMPLE_PAYLOAD
    assert card["headline"] and card["reason"] and card["source"] in {"model", "template"}


def test_second_request_for_the_same_card_reruns_nothing(parts):
    engine, pipeline, svc = parts
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    first = svc.card("rfc-62-01", "es", "casual")
    second = svc.card("rfc-62-01", "es", "casual")
    assert first == second
    assert len(engine.calls) == 1
    assert pipeline.calls == [("rfc-62-01", "es", "casual")]


def test_other_locale_or_mode_runs_the_pipeline_but_not_the_engine(parts):
    engine, pipeline, svc = parts
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    svc.card("rfc-62-01", "en", "casual")
    svc.card("rfc-62-01", "en", "analyst")
    svc.card("rfc-62-01", "es", "casual")
    assert len(engine.calls) == 1 and len(pipeline.calls) == 3


def test_a_decision_reopened_with_other_numbers_is_narrated_again(parts):
    """The live runner reopens the same ids in every replay of the demo match; a card narrated
    for an earlier run's numbers (a run joined mid-match) must not be served with them."""
    _, pipeline, _ = parts
    payloads = iter([SAMPLE_PAYLOAD, {**SAMPLE_PAYLOAD, "options": SAMPLE_PAYLOAD["options"][::-1]}])
    svc = CardService(lambda snapshot, team, trigger: next(payloads), pipeline, MemoryStore())
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    assert svc.card("rfc-62-01", "en", "casual")["payload"] == SAMPLE_PAYLOAD
    second = svc.open(SNAPSHOT, "RFC", "condition_drop")
    assert svc.card("rfc-62-01", "en", "casual")["payload"] == second
    assert len(pipeline.calls) == 2


def test_a_decision_reopened_with_the_same_numbers_keeps_its_narration(parts):
    _, pipeline, svc = parts
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    first = svc.card("rfc-62-01", "en", "casual")
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    assert svc.card("rfc-62-01", "en", "casual") == first
    assert len(pipeline.calls) == 1


def test_unknown_decision_is_none(parts):
    _, pipeline, svc = parts
    assert svc.card("nope", "en", "casual") is None
    assert pipeline.calls == []


@pytest.mark.parametrize("locale,mode", [("fr", "casual"), ("en", "loud")])
def test_unsupported_locale_or_mode_is_rejected(parts, locale, mode):
    _, _, svc = parts
    svc.open(SNAPSHOT, "RFC", "condition_drop")
    with pytest.raises(ValueError):
        svc.card("rfc-62-01", locale, mode)


def test_default_service_narrates_with_the_stub_without_foundry_settings(monkeypatch):
    for name in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"):
        monkeypatch.delenv(name, raising=False)
    from dugout.service.cards import default_service
    assert isinstance(default_service()._pipeline._client, StubClient)


def test_default_service_narrates_with_foundry_when_configured(monkeypatch):
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://dugout-test.openai.azure.com")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5-mini")
    from dugout.agents.foundry import FoundryClient
    from dugout.agents.workflow import NarrationWorkflow
    from dugout.service.cards import default_service
    pipeline = default_service()._pipeline
    assert isinstance(pipeline, NarrationWorkflow)
    assert isinstance(pipeline._client, FoundryClient)
