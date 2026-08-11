import json
from io import BytesIO
from urllib.error import HTTPError

from services.crm_service.client import CRMClient


def _configure_jira_env(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "jira")
    monkeypatch.setenv("CRM_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("CRM_API_TOKEN", "token-123")
    monkeypatch.setenv("CRM_USER_EMAIL", "agent@example.com")
    monkeypatch.setenv("CRM_PROJECT_KEY", "OP")
    monkeypatch.setenv("CRM_ISSUE_TYPE", "Service Request")


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_create_jira_ticket_returns_key_and_url(monkeypatch):
    _configure_jira_env(monkeypatch)
    client = CRMClient()

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["headers"] = dict(request.header_items())
        return _FakeResponse({"key": "OP-15"})

    monkeypatch.setattr("services.crm_service.client.urlopen", fake_urlopen)

    result = client.create_jira_ticket(
        summary="Customer needs help",
        description="Full description here",
        priority="High",
        labels=["complaint", "omnichannel-cx"],
    )

    assert result.status == "synced"
    assert result.data["external_ticket_id"] == "OP-15"
    assert result.data["external_ticket_url"] == "https://example.atlassian.net/browse/OP-15"
    assert captured["url"] == "https://example.atlassian.net/rest/api/3/issue"
    assert captured["payload"]["fields"]["project"] == {"key": "OP"}
    assert captured["payload"]["fields"]["summary"] == "Customer needs help"
    assert captured["payload"]["fields"]["issuetype"] == {"name": "Service Request"}
    assert captured["payload"]["fields"]["priority"] == {"name": "High"}
    assert captured["payload"]["fields"]["labels"] == ["complaint", "omnichannel-cx"]
    assert "Authorization" in captured["headers"] or "Authorization".lower() in [k.lower() for k in captured["headers"]]


def test_create_jira_ticket_omits_priority_when_not_given(monkeypatch):
    _configure_jira_env(monkeypatch)
    client = CRMClient()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return _FakeResponse({"key": "OP-16"})

    monkeypatch.setattr("services.crm_service.client.urlopen", fake_urlopen)

    client.create_jira_ticket(summary="s", description="d")

    assert "priority" not in captured["payload"]["fields"]


def test_create_jira_ticket_surfaces_http_error_details(monkeypatch):
    _configure_jira_env(monkeypatch)
    client = CRMClient()

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url, 400,
            "Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"errors":{"issuetype":"Specify a valid issue type"}}'),
        )

    monkeypatch.setattr("services.crm_service.client.urlopen", fake_urlopen)

    result = client.create_jira_ticket(summary="s", description="d")

    assert result.status == "failed"
    assert "Specify a valid issue type" in result.error


def test_create_jira_ticket_not_configured_without_required_fields(monkeypatch):
    monkeypatch.setenv("CRM_PROVIDER", "jira")
    monkeypatch.delenv("CRM_BASE_URL", raising=False)
    client = CRMClient()

    result = client.create_jira_ticket(summary="s", description="d")

    assert result.status == "not_configured"


def test_create_ticket_delegates_to_create_jira_ticket_for_jira_provider(monkeypatch):
    """Regression guard: create_ticket() (used by the orchestration/HITL flow) and the
    directly-callable create_jira_ticket() must share one payload-building code path."""
    _configure_jira_env(monkeypatch)
    from shared.schemas.tickets import Ticket, TicketPriority

    client = CRMClient()
    captured = {}

    def fake_create_jira_ticket(self, summary, description, priority=None, labels=None):
        captured.update(summary=summary, description=description, priority=priority, labels=labels)
        from services.crm_service.client import CRMResult
        return CRMResult("synced", {"key": "OP-99"})

    monkeypatch.setattr(CRMClient, "create_jira_ticket", fake_create_jira_ticket)

    ticket = Ticket(
        ticket_id="tkt-1", conversation_id="conv-1", customer_id="cust-1",
        title="Fraud report", description="Unauthorized transaction",
        intent="fraud_report", priority=TicketPriority.CRITICAL, assigned_team="fraud_and_disputes",
    )
    result = client.create_ticket(ticket)

    assert result.data["key"] == "OP-99"
    assert captured["summary"] == "Fraud report"
    assert captured["priority"] == "Critical"
    assert captured["labels"] == ["fraud_report", "omnichannel-cx"]
