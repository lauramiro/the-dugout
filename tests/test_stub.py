from fastapi.testclient import TestClient

from dugout.stub.app import SAMPLE_DECISION, app, get_publisher


class FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, payload):
        self.sent.append(payload)

    def client_url(self):
        return "wss://example.invalid/client/hubs/decisions"


def client(publisher):
    app.dependency_overrides[get_publisher] = lambda: publisher
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_decision_returns_the_sample_payload():
    body = client(None).get("/decision").json()
    assert body == SAMPLE_DECISION
    assert body["decision_id"] == "rfc-62-01"
    assert body["recommendation"] == {"option_id": "sub_lb", "strength": "strong"}


def test_push_publishes_the_payload():
    pub = FakePublisher()
    body = client(pub).post("/push").json()
    assert body["pushed"] is True
    assert pub.sent == [SAMPLE_DECISION]


def test_push_without_web_pubsub_reports_not_pushed():
    body = client(None).post("/push").json()
    assert body["pushed"] is False
    assert body["decision"] == SAMPLE_DECISION


def test_negotiate_returns_client_url():
    assert client(FakePublisher()).get("/negotiate").json() == {
        "url": "wss://example.invalid/client/hubs/decisions"
    }


def test_healthz():
    assert client(None).get("/healthz").json() == {"ok": True}
