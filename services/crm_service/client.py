from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from shared.schemas.tickets import Ticket

logger = logging.getLogger(__name__)


@dataclass
class CRMResult:
    status: str
    data: dict
    error: str | None = None


class CRMClient:
    """Optional CRM and ticket-system REST integration.

    Generic mode targets a conventional CRM REST API. Jira mode uses Atlassian
    issue payloads adapted from the Ticketmate prototype.
    """

    def __init__(self) -> None:
        self.provider = os.getenv("CRM_PROVIDER", "disabled").lower()
        self.base_url = os.getenv("CRM_BASE_URL", "").rstrip("/")
        self.api_token = os.getenv("CRM_API_TOKEN", "")
        self.user_email = os.getenv("CRM_USER_EMAIL", "")
        self.project_key = os.getenv("CRM_PROJECT_KEY", "")
        self.issue_type = os.getenv("CRM_ISSUE_TYPE", "Task")
        self.timeout = int(os.getenv("CRM_TIMEOUT_SECONDS", "15"))
        self.retries = int(os.getenv("CRM_MAX_RETRIES", "2"))

    @property
    def configured(self) -> bool:
        if self.provider == "jira":
            return all((self.base_url, self.api_token, self.user_email, self.project_key))
        if self.provider == "generic":
            return bool(self.base_url and self.api_token)
        return False

    def lookup_customer(self, channel: str, identifier: str) -> CRMResult:
        if not self.configured:
            return CRMResult("not_configured", {})
        if self.provider == "jira":
            return CRMResult("not_supported", {})
        query = urlencode({"channel": channel, "identifier": identifier})
        return self._request("GET", f"/customers/resolve?{query}")

    def create_ticket(self, ticket: Ticket, customer: dict | None = None) -> CRMResult:
        if not self.configured:
            return CRMResult("not_configured", {})
        if self.provider == "jira":
            return self.create_jira_ticket(
                summary=ticket.title,
                description=ticket.description,
                priority=ticket.priority.value.title(),
                labels=[ticket.intent, "omnichannel-cx"],
            )
        payload = {
            "external_reference": ticket.ticket_id,
            "customer": customer or {},
            "title": ticket.title,
            "description": ticket.description,
            "intent": ticket.intent,
            "priority": ticket.priority.value,
            "assigned_team": ticket.assigned_team,
            "sla_due_at": ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
            "metadata": ticket.metadata,
        }
        result = self._request("POST", "/tickets", payload)
        if result.status == "synced":
            result.data["external_ticket_id"] = result.data.get("ticket_id") or result.data.get("id")
            result.data["external_ticket_url"] = result.data.get("url")
        return result

    def create_jira_ticket(
        self,
        summary: str,
        description: str,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> CRMResult:
        """Low-level Jira issue creation primitive (POST /rest/api/3/issue).

        This is the single place that builds a Jira issue payload — create_ticket()'s
        jira branch calls this too, so there is only one code path to fix if Atlassian's
        API shape changes. Returns a CRMResult whose .data carries external_ticket_id
        (the issue key, e.g. "OP-15") and external_ticket_url on success.
        """
        if not self.configured or self.provider != "jira":
            return CRMResult("not_configured", {})
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": self._adf_from_text(description),
                "issuetype": {"name": self.issue_type},
                "labels": list(labels or []),
            }
        }
        if priority:
            payload["fields"]["priority"] = {"name": priority}
        result = self._request("POST", "/rest/api/3/issue", payload)
        if result.status == "synced":
            key = result.data.get("key")
            result.data["external_ticket_id"] = key
            result.data["external_ticket_url"] = f"{self.base_url}/browse/{key}" if key else None
        return result

    def add_comment(self, external_ticket_id: str, comment: str) -> CRMResult:
        if not self.configured:
            return CRMResult("not_configured", {})
        if self.provider == "jira":
            return self._request(
                "POST",
                f"/rest/api/3/issue/{quote(external_ticket_id)}/comment",
                {"body": self._adf_from_text(comment)},
            )
        return self._request("POST", f"/tickets/{quote(external_ticket_id)}/comments", {"comment": comment})

    def update_ticket_status(self, external_ticket_id: str, status: str) -> CRMResult:
        if not self.configured:
            return CRMResult("not_configured", {})
        if self.provider == "jira":
            transitions = self._request("GET", f"/rest/api/3/issue/{quote(external_ticket_id)}/transitions")
            if transitions.status != "synced":
                return transitions
            match = next(
                (
                    item for item in transitions.data.get("transitions", [])
                    if item.get("name", "").lower() == status.lower()
                    or item.get("to", {}).get("name", "").lower() == status.lower()
                ),
                None,
            )
            if not match:
                return CRMResult("failed", {}, f"No Jira transition found for status '{status}'")
            return self._request(
                "POST",
                f"/rest/api/3/issue/{quote(external_ticket_id)}/transitions",
                {"transition": {"id": match["id"]}},
            )
        return self._request("PATCH", f"/tickets/{quote(external_ticket_id)}", {"status": status})

    def _request(self, method: str, path: str, payload: dict | None = None) -> CRMResult:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(1, self.retries + 2):
            try:
                request = Request(
                    f"{self.base_url}{path}",
                    data=body,
                    method=method,
                    headers=self._headers(),
                )
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    return CRMResult("synced", json.loads(raw) if raw else {})
            except ValueError as exc:
                error = f"CRM {method} {path} has an invalid URL: {exc}"
                logger.error(error)
                return CRMResult("failed", {}, error)
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                error = f"CRM {method} {path} failed with {exc.code}: {detail}"
                if exc.code < 500 or attempt > self.retries:
                    logger.error(error)
                    return CRMResult("failed", {}, error)
            except (URLError, TimeoutError, OSError) as exc:
                error = f"CRM {method} {path} failed: {exc}"
                if attempt > self.retries:
                    logger.error(error)
                    return CRMResult("failed", {}, error)
            time.sleep(0.2 * attempt)
        return CRMResult("failed", {}, "CRM request failed")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.provider == "jira":
            credentials = base64.b64encode(f"{self.user_email}:{self.api_token}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    @staticmethod
    def _adf_from_text(text: str | None) -> dict[str, Any]:
        lines = (text or "No description provided.").splitlines() or [""]
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": line or " "}]}
                for line in lines
            ],
        }
