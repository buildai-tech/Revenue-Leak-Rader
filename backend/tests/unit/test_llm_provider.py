"""
Unit tests for the LLM provider layer (NVIDIA NIM via OpenAI-compatible API).

Regression coverage for the 2026-09-05 production incident: the `openai`
package was missing from requirements.txt, so constructing NvidiaLLMProvider
raised ModuleNotFoundError on every AI column-mapping request.

These tests pin down:
- NvidiaLLMProvider constructs cleanly when `openai` is installed
- get_llm_provider() honours LLM_PROVIDER=nvidia + credentials from settings
- suggest_column_mappings parses a well-formed JSON array from the model
- malformed model output falls back to deterministic heuristics
- provider-level failures propagate to the caller (the API layer owns the
  graceful heuristic fallback — see test_ai_mapping_fallback.py)
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.ai import llm_provider as llm_provider_module
from app.ai.llm_provider import NvidiaLLMProvider, NoOpLLMProvider, get_llm_provider

NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"
FAKE_KEY = "nvapi-unit-test-key"  # not a real credential


# ── Fakes for the OpenAI-compatible client ────────────────────────────────
class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


def _fake_client(content: str) -> tuple[SimpleNamespace, _FakeCompletions]:
    completions = _FakeCompletions(content)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


# ── Construction / factory ────────────────────────────────────────────────
def test_nvidia_provider_initializes_when_openai_installed():
    """The openai SDK must be importable and the provider must construct
    without touching the network."""
    try:
        import openai
    except ModuleNotFoundError:  # pragma: no cover
        pytest.fail(
            "The openai package is not installed — it must be in "
            "requirements.txt (production incident 2026-09-05)."
        )

    provider = NvidiaLLMProvider(api_key=FAKE_KEY, model=NVIDIA_MODEL)
    assert provider._model == NVIDIA_MODEL
    assert isinstance(provider._client, openai.AsyncOpenAI)


def test_get_llm_provider_returns_nvidia_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("NVIDIA_MODEL", NVIDIA_MODEL)
    llm_provider_module.get_settings.cache_clear()
    try:
        provider = get_llm_provider()
    finally:
        llm_provider_module.get_settings.cache_clear()

    assert isinstance(provider, NvidiaLLMProvider)
    assert provider._model == NVIDIA_MODEL


def test_get_llm_provider_defaults_to_noop(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "noop")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    llm_provider_module.get_settings.cache_clear()
    try:
        provider = get_llm_provider()
    finally:
        llm_provider_module.get_settings.cache_clear()

    assert isinstance(provider, NoOpLLMProvider)


# ── suggest_column_mappings behaviour ─────────────────────────────────────
@pytest.mark.asyncio
async def test_nvidia_provider_suggest_column_mappings_success():
    provider = NvidiaLLMProvider(api_key=FAKE_KEY, model=NVIDIA_MODEL)
    client, completions = _fake_client('[{"source": "Email", "target": "email"}]')
    provider._client = client

    result = await provider.suggest_column_mappings(
        ["Email", "Phone"], ["email", "phone_raw"], [{"Email": "a@b.com"}],
    )

    assert result == [{"source": "Email", "target": "email"}]
    assert completions.calls, "expected exactly one chat completion call"
    call_kwargs = completions.calls[0]
    assert call_kwargs["model"] == NVIDIA_MODEL
    assert call_kwargs["temperature"] == 0
    assert FAKE_KEY not in str(call_kwargs), "credentials must never leak into requests"


@pytest.mark.asyncio
async def test_nvidia_provider_malformed_json_falls_back_to_heuristic():
    from app.ai.column_mapper import TARGET_FIELDS, heuristic_suggest

    provider = NvidiaLLMProvider(api_key=FAKE_KEY, model=NVIDIA_MODEL)
    client, _ = _fake_client("this is not JSON at all")
    provider._client = client

    columns = ["Lead Name", "Email", "Phone"]
    result = await provider.suggest_column_mappings(columns, TARGET_FIELDS, [])

    assert result == heuristic_suggest(columns, TARGET_FIELDS)


@pytest.mark.asyncio
async def test_nvidia_provider_failure_propagates_to_caller():
    """Provider-level exceptions (auth, network, missing SDK) propagate —
    the API layer owns the graceful fallback."""
    provider = NvidiaLLMProvider(api_key=FAKE_KEY, model=NVIDIA_MODEL)

    async def _boom(**kwargs: Any):
        raise RuntimeError("simulated NVIDIA outage")

    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_boom))
    )

    with pytest.raises(RuntimeError):
        await provider.suggest_column_mappings(["Email"], ["email"], [])


@pytest.mark.asyncio
async def test_noop_provider_suggests_without_any_api_key():
    provider = NoOpLLMProvider()
    result = await provider.suggest_column_mappings(["Email"], ["email"], [])
    assert isinstance(result, list)