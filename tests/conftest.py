"""Network guard for the test suite.

WHY THIS EXISTS
---------------
Measured on 2026-09-01, a single `pytest` run made **10 real Groq `_generate` calls**
and **30 real POSTs to production Jira** (`promptlings.atlassian.net`). The Jira calls
returned 400, were swallowed as `crm_sync_failed`, and every test carried on — which is
why it went unnoticed for the life of the project. The Groq calls were billed against
the demo's 500K/day free-tier quota.

Three independent causes, all the same shape (`x or RealClient()` with no way to inject):
  1. `TicketCreationAgent`  -> `generator or GroqGenerator()`
  2. `OrchestrationGraph`   -> `crm or CRMClient()`, and CRM_PROVIDER in .env is jira
  3. `QueryResolutionAgent` -> `rag or RAGPipeline()` -> real GroqGenerator

Those are fixed by injection at the call sites. This file is the guard that stops a
NEW test from silently reopening the hole: it patches the outermost network boundary
so an un-injected client fails loudly instead of spending money.

WHAT IT DOES NOT DO
-------------------
It does not patch `GroqGenerator._generate` or `CRMClient.create_ticket` themselves —
some tests legitimately exercise those methods with their own fakes injected
underneath (e.g. test_groq_generator_records_local_llm_usage swaps in a fake client,
and test_create_ticket_delegates_to_create_jira_ticket_for_jira_provider monkeypatches
create_jira_ticket). Guarding the transport layer instead lets those pass untouched
while still blocking anything that would actually reach the network.
"""
import pytest


class RealNetworkCallInTest(RuntimeError):
    """Raised when a test tries to reach a real external service."""


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch, request):
    """Fail loudly on any HTTP request or Groq SDK call that escapes a test."""

    def _fail(service):
        def boom(*args, **kwargs):
            raise RealNetworkCallInTest(
                f"Test '{request.node.name}' tried to call {service} for real.\n"
                "Inject a fake instead — see tests/test_phase1.py FakeGenerator / offline_crm(), "
                "and pass generator=/crm= when constructing OrchestrationGraph."
            )
        return boom

    # HTTP transport — covers the Jira/CRM path (requests) and anything else using it.
    try:
        import requests
        for verb in ("get", "post", "put", "patch", "delete", "request"):
            monkeypatch.setattr(requests, verb, _fail("Jira/HTTP"), raising=False)
        monkeypatch.setattr(requests.Session, "request", _fail("Jira/HTTP"), raising=False)
    except ImportError:
        pass

    # Groq SDK — the constructor, so an un-injected GroqGenerator fails at build time
    # rather than silently holding a live client.
    try:
        import groq
        monkeypatch.setattr(groq, "Groq", _fail("Groq"), raising=False)
    except ImportError:
        pass

    yield
