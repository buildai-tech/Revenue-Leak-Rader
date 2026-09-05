"""
LLM Provider interface + NoOpLLMProvider + NvidiaLLMProvider.

The LLM is used ONLY for:
1. Column-mapping suggestions (human must confirm)
2. Recommendation copy personalization
3. Evidence-explanation prose

The LLM must NEVER:
- Calculate financial values
- Determine tiers
- Decide whether a lead is leaking
- Calculate the Lead Recovery Score
- Calculate response-time statistics
- Fabricate evidence
- Select which recommendation playbook applies

This module must NOT import SQLAlchemy models for financial_calculations,
leakage_events, or recovery_outcomes.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from app.config import get_settings


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def suggest_column_mappings(
        self, source_columns: list[str], target_fields: list[str], sample_data: list[dict]
    ) -> list[dict[str, Any]]:
        """Suggest mappings from source columns to target fields."""
        ...

    @abstractmethod
    async def personalize_recommendation(
        self, template: str, lead_context: dict[str, Any]
    ) -> str:
        """Personalize a recommendation template with lead-specific context."""
        ...

    @abstractmethod
    async def explain_evidence(
        self, evidence_items: list[dict[str, Any]]
    ) -> str:
        """Generate a human-readable explanation of evidence items."""
        ...


class NoOpLLMProvider(LLMProvider):
    """Fallback provider that returns deterministic, template-based responses.

    The entire app works correctly with this provider. No API key needed.
    """

    async def suggest_column_mappings(
        self, source_columns: list[str], target_fields: list[str], sample_data: list[dict]
    ) -> list[dict[str, Any]]:
        """Use heuristic matching when LLM is unavailable."""
        from app.ai.column_mapper import heuristic_suggest
        return heuristic_suggest(source_columns, target_fields)

    async def personalize_recommendation(
        self, template: str, lead_context: dict[str, Any]
    ) -> str:
        """Return the template as-is with basic variable substitution."""
        result = template
        for key, value in lead_context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    async def explain_evidence(
        self, evidence_items: list[dict[str, Any]]
    ) -> str:
        """Return a simple bulleted list of evidence."""
        lines = []
        for item in evidence_items:
            lines.append(f"• {item.get('type', 'unknown')}: {item.get('detail', '')}")
        return "\n".join(lines) if lines else "No evidence items provided."


class NvidiaLLMProvider(LLMProvider):
    """LLM provider backed by NVIDIA NIM (OpenAI-compatible API).

    Uses the same openai Python SDK but points base_url at NVIDIA's endpoint.
    Requires NVIDIA_API_KEY to be set in the environment.
    """

    def __init__(self, api_key: str, model: str) -> None:
        # Import here so the openai package is only required when this provider
        # is actually selected — the rest of the app works without it.
        from openai import AsyncOpenAI  # type: ignore[import]

        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://integrate.api.nvidia.com/v1",
        )

    async def suggest_column_mappings(
        self, source_columns: list[str], target_fields: list[str], sample_data: list[dict]
    ) -> list[dict[str, Any]]:
        """Ask the model to suggest column → field mappings as JSON."""
        prompt = (
            f"Map these source CSV columns to the target fields.\n"
            f"Source columns: {source_columns}\n"
            f"Target fields: {target_fields}\n"
            f"Sample row: {sample_data[0] if sample_data else {}}\n"
            "Reply ONLY with a JSON array of objects with keys "
            '"source" and "target". No markdown fences.'
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "[]"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to heuristic if the model returns garbage
            from app.ai.column_mapper import heuristic_suggest
            return heuristic_suggest(source_columns, target_fields)

    async def personalize_recommendation(
        self, template: str, lead_context: dict[str, Any]
    ) -> str:
        """Use the model to personalise the recommendation copy."""
        prompt = (
            f"Personalise the following recommendation for the lead context provided.\n"
            f"Template: {template}\n"
            f"Lead context: {lead_context}\n"
            "Reply ONLY with the personalised text, no extra commentary."
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
        )
        return response.choices[0].message.content or template

    async def explain_evidence(
        self, evidence_items: list[dict[str, Any]]
    ) -> str:
        """Use the model to write a concise explanation of the evidence."""
        prompt = (
            "Write a concise, plain-English explanation of the following "
            f"revenue-leakage evidence items: {evidence_items}\n"
            "Keep it under 120 words, no bullet points."
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=256,
        )
        return response.choices[0].message.content or "No explanation available."


def get_llm_provider() -> LLMProvider:
    """Factory function — returns the configured LLM provider.

    Supported values for LLM_PROVIDER env var:
      "noop"   — no API key needed, deterministic template-based responses (default)
      "nvidia" — NVIDIA NIM (OpenAI-compatible). Requires NVIDIA_API_KEY.
    """
    settings = get_settings()

    if settings.LLM_PROVIDER == "nvidia":
        if not settings.NVIDIA_API_KEY:
            import logging
            logging.getLogger(__name__).warning(
                "LLM_PROVIDER=nvidia but NVIDIA_API_KEY is not set — "
                "falling back to NoOpLLMProvider."
            )
            return NoOpLLMProvider()
        return NvidiaLLMProvider(
            api_key=settings.NVIDIA_API_KEY,
            model=settings.NVIDIA_MODEL,
        )

    # Default / explicit noop
    return NoOpLLMProvider()
