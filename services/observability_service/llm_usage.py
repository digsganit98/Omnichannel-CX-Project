from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_LLM_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("llm_observation_context", default={})

_DEFAULT_RATES_PER_MILLION = {
    # Groq public rates, read from the live /v1/models endpoint (which reports USD
    # per token) and converted to per-million here. Override with LLM_COST_RATES_JSON
    # when exact commercial rates differ.
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.3},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.6},
    # Retired: the Llama models were removed from Groq and now 404. Kept so existing
    # llm_usage_events rows recorded against them still cost out in the analytics panel.
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
}


@contextmanager
def llm_observation_context(**values: Any) -> Iterator[None]:
    current = dict(_LLM_CONTEXT.get() or {})
    current.update({key: value for key, value in values.items() if value is not None})
    token = _LLM_CONTEXT.set(current)
    try:
        # conversation_id/customer_id map to Langfuse's own session_id/user_id (not just
        # metadata) so this conversation groups under Sessions and this customer's calls
        # roll up under Users/cost-attribution in the Langfuse UI.
        with _propagate_langfuse_attributes(current):
            yield
    finally:
        _LLM_CONTEXT.reset(token)


def _propagate_langfuse_attributes(context: dict[str, Any]):
    if not _langfuse_configured():
        return nullcontext()
    try:
        from langfuse import propagate_attributes
    except Exception:
        logger.exception("langfuse_propagate_attributes_import_failed")
        return nullcontext()

    kwargs: dict[str, Any] = {}
    if context.get("conversation_id"):
        kwargs["session_id"] = str(context["conversation_id"])
    if context.get("customer_id"):
        kwargs["user_id"] = str(context["customer_id"])
    tags = sorted({str(value) for value in (context.get("channel"), context.get("intent")) if value})
    if tags:
        kwargs["tags"] = tags
    if not kwargs:
        return nullcontext()

    try:
        return propagate_attributes(**kwargs)
    except Exception:
        logger.exception("langfuse_propagate_attributes_failed")
        return nullcontext()


@contextmanager
def langfuse_workflow_trace(
    *,
    name: str,
    input_text: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Iterator[Any | None]:
    if not _langfuse_configured():
        yield None
        return
    try:
        from langfuse import get_client, propagate_attributes

        client = get_client()
        capture_io = os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true"
        with client.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_text if capture_io else None,
            metadata=metadata or {},
        ) as span:
            # Tag the whole message even when no LLM call happens inside (e.g. a pure
            # ticket-status shortcut) so it's still filterable by channel in the UI.
            with propagate_attributes(tags=tags) if tags else nullcontext():
                token = _merge_context(_current_langfuse_context(client))
                try:
                    yield span
                finally:
                    _LLM_CONTEXT.reset(token)
    except Exception:
        logger.exception("langfuse_workflow_trace_failed")
        yield None


def flush_langfuse() -> None:
    """Flush buffered Langfuse events before process exit (e.g. FastAPI shutdown).

    The SDK batches and exports asynchronously; without an explicit flush, traces
    generated shortly before shutdown can be dropped instead of reaching Langfuse.
    """
    if not _langfuse_configured():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        logger.exception("langfuse_flush_failed")


def langfuse_status(check_auth: bool = False) -> dict:
    status = {
        "enabled": os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
        "public_key_configured": bool(os.getenv("LANGFUSE_PUBLIC_KEY")),
        "secret_key_configured": bool(os.getenv("LANGFUSE_SECRET_KEY")),
        "base_url": os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
        "capture_io": os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true",
        "authenticated": None,
    }
    if not check_auth or not _langfuse_configured():
        return status
    try:
        from langfuse import get_client

        status["authenticated"] = bool(get_client().auth_check())
    except Exception as exc:
        status["authenticated"] = False
        status["error"] = str(exc)
    return status


def record_llm_call(
    *,
    provider: str,
    model: str,
    operation: str,
    llm_used: bool,
    latency_ms: float | None,
    response: Any = None,
    output_text: str = "",
    input_text: str = "",
    error: str | None = None,
    metadata: dict | None = None,
    params: dict | None = None,
) -> dict:
    usage = _extract_usage(response)
    estimated_cost = _estimate_cost_usd(model, usage["prompt_tokens"], usage["completion_tokens"])
    # model_version = a short fingerprint of OUR config (model + the sampling params actually
    # sent to the provider). Changing any param → a new version tag, so cost/latency can be
    # sliced by exact configuration over time. Falls back to the provider's system_fingerprint
    # when no params are supplied (keeps older call sites working).
    model_config = _normalize_params(model, params)
    model_version = _config_version(model_config) if model_config else _extract_model_version(response)
    context = dict(_LLM_CONTEXT.get() or {})
    langfuse_context = _current_langfuse_context()
    safe_metadata = {
        **(metadata or {}),
        **langfuse_context,
        "input_chars": len(input_text or ""),
        "output_chars": len(output_text or ""),
        "usage_source": usage["source"],
        "cost_rate_source": estimated_cost["source"],
    }
    # Log the full config alongside the tag so v-xxxx is always decodable ("log it somewhere").
    if model_config:
        safe_metadata["model_config"] = model_config
    event = {
        **context,
        "operation": operation,
        "provider": provider,
        "model": model,
        "model_version": model_version,
        "llm_used": llm_used,
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "estimated_cost_usd": estimated_cost["cost_usd"],
        "latency_ms": latency_ms,
        "status": "success" if llm_used and not error else "failed",
        "error": error,
        "metadata": safe_metadata,
    }
    _persist_event(event)
    _send_langfuse_event(
        event,
        input_text=input_text,
        output_text=output_text,
    )
    return event


def _persist_event(event: dict) -> None:
    if os.getenv("LLM_OBSERVABILITY_ENABLED", "true").lower() != "true":
        return
    try:
        from services.persistence_service.repository import SQLiteCXRepository

        SQLiteCXRepository(os.getenv("DATABASE_PATH", "data/cx_phase1.db")).add_llm_usage_event(event)
    except Exception:
        logger.exception("llm_usage_persist_failed")


def _send_langfuse_event(event: dict, *, input_text: str, output_text: str) -> None:
    if not _langfuse_configured():
        return
    try:
        from langfuse import get_client

        client = get_client()
        capture_io = os.getenv("LANGFUSE_CAPTURE_IO", "false").lower() == "true"
        metadata = {
            **(event.get("metadata") or {}),
            "correlation_id": event.get("correlation_id"),
            "conversation_id": event.get("conversation_id"),
            "customer_id": event.get("customer_id"),
            "message_id": event.get("message_id"),
            "channel": event.get("channel"),
            "agent": event.get("agent"),
            "intent": event.get("intent"),
            "resolution_level": event.get("resolution_level"),
            "ticket_id": event.get("ticket_id"),
            "retrieval_backend": event.get("retrieval_backend"),
            "latency_ms": event.get("latency_ms"),
            "estimated_cost_usd": event.get("estimated_cost_usd"),
        }
        with client.start_as_current_observation(
            as_type="generation",
            name=event.get("operation") or "llm_call",
            model=event.get("model") or "unknown",
            input=input_text if capture_io else None,
            metadata=metadata,
        ) as generation:
            generation.update(
                output=output_text if capture_io else None,
                usage_details={
                    "input": event.get("prompt_tokens") or 0,
                    "output": event.get("completion_tokens") or 0,
                    "total": event.get("total_tokens") or 0,
                },
                cost_details={"total": event.get("estimated_cost_usd") or 0.0},
                level="ERROR" if event.get("status") == "failed" else "DEFAULT",
                status_message=event.get("error"),
            )
    except Exception:
        # Observability must never break customer response handling.
        logger.exception("langfuse_export_failed")


def _langfuse_configured() -> bool:
    return (
        os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
        and bool(os.getenv("LANGFUSE_SECRET_KEY"))
    )


def _merge_context(values: dict[str, Any]):
    current = dict(_LLM_CONTEXT.get() or {})
    current.update({key: value for key, value in values.items() if value is not None})
    return _LLM_CONTEXT.set(current)


def _current_langfuse_context(client: Any | None = None) -> dict[str, str]:
    if not _langfuse_configured():
        return {}
    try:
        if client is None:
            from langfuse import get_client

            client = get_client()
        trace_id = client.get_current_trace_id()
        if not trace_id:
            return {}
        return {
            "langfuse_trace_id": trace_id,
            "langfuse_trace_url": client.get_trace_url(trace_id=trace_id),
        }
    except Exception:
        return {}


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = _get(response, "usage", None)
    prompt = _int(_get(usage, "prompt_tokens", 0))
    completion = _int(_get(usage, "completion_tokens", 0))
    total = _int(_get(usage, "total_tokens", prompt + completion))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "source": "provider_usage" if usage else "not_available",
    }


def _normalize_params(model: str, params: dict | None) -> dict | None:
    """Build the config dict that defines a 'version': model + the sampling params actually sent.

    Only includes keys that were genuinely passed (per the user's 'hash what's actually sent'
    choice), so adding a param later naturally produces a new version. Returns None when no
    params dict is supplied at all (older call sites), so behaviour is unchanged there.
    """
    if params is None:
        return None
    allowed = ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty")
    cfg: dict[str, Any] = {"model": model}
    for key in allowed:
        if key in params and params[key] is not None:
            cfg[key] = params[key]
    return cfg


def _config_version(model_config: dict) -> str:
    """Short, stable tag for a config dict — 'v-' + first 4 hex of a sha256 over the sorted config.

    Deterministic: same config → same tag; any change to model or a param → a new tag.
    """
    import hashlib

    payload = json.dumps(model_config, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "v-" + digest[:4]


def _extract_model_version(response: Any) -> str | None:
    """Best-effort model build/version identifier (e.g. OpenAI-compatible system_fingerprint).

    Model name alone (e.g. "llama-3.1-8b-instant") doesn't capture which underlying
    build served the request; providers that rev their weights/serving stack expose
    that here so cost/latency can be sliced by exact model build over time.
    """
    return _get(response, "system_fingerprint", None)


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    rates = _rates()
    rate = rates.get(model) or rates.get(str(model or "").lower())
    if not rate:
        return {"cost_usd": 0.0, "source": "rate_not_configured"}
    input_rate = float(rate.get("input", 0.0))
    output_rate = float(rate.get("output", 0.0))
    cost = (prompt_tokens * input_rate / 1_000_000) + (completion_tokens * output_rate / 1_000_000)
    return {"cost_usd": round(cost, 8), "source": "env_config" if _env_rates() else "default_config"}


def _rates() -> dict[str, dict[str, float]]:
    custom = _env_rates()
    if custom:
        normalized = {}
        for model, value in custom.items():
            if isinstance(value, dict):
                normalized[model] = {
                    "input": float(value.get("input", value.get("prompt", 0.0)) or 0.0),
                    "output": float(value.get("output", value.get("completion", 0.0)) or 0.0),
                }
                normalized[model.lower()] = normalized[model]
        return normalized
    return {
        **_DEFAULT_RATES_PER_MILLION,
        **{model.lower(): rate for model, rate in _DEFAULT_RATES_PER_MILLION.items()},
    }


def _env_rates() -> dict | None:
    raw = os.getenv("LLM_COST_RATES_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        logger.warning("llm_cost_rates_json_invalid")
        return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
