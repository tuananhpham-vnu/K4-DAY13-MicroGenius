from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .prompt_management import resolve_prompt
from .tracing import get_langfuse_client, observe, tracing_enabled

# USD per 1M tokens. Gemini pricing is a placeholder - confirm against
# https://ai.google.dev/gemini-api/docs/pricing before trusting cost_usd.
PRICE_PER_MILLION_TOKENS = {
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "gemini": {"input": 0.1, "output": 0.4},
}


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str | None = None) -> None:
        provider = os.getenv("LLM_PROVIDER", "auto").lower()
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        use_gemini = provider == "gemini" or (provider == "auto" and bool(gemini_api_key))
        max_output_tokens = self._parse_int_env("COST_GUARD_MAX_OUTPUT_TOKENS")

        if use_gemini:
            from .gemini_llm import GeminiLLM

            self.model = model or os.getenv("GEMINI_PROVIDER", "gemini-2.0-flash")
            self.llm = GeminiLLM(model=self.model, api_key=gemini_api_key, max_output_tokens=max_output_tokens)
            self._pricing = PRICE_PER_MILLION_TOKENS["gemini"]
        else:
            self.model = model or "claude-sonnet-4-5"
            self.llm = FakeLLM(model=self.model, max_output_tokens=max_output_tokens)
            self._pricing = PRICE_PER_MILLION_TOKENS["claude-sonnet-4-5"]

        # Exact-match response cache: repeat (feature, message) pairs skip the LLM call
        # entirely, saving cost. Best demonstrated with repeated/duplicate traffic.
        self._response_cache: dict[str, AgentResult] = {}

    @staticmethod
    def _parse_int_env(name: str) -> int | None:
        raw = os.getenv(name)
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @observe(as_type="generation", capture_input=False, capture_output=False)
    def run(self, user_id: str, feature: str, session_id: str, message: str) -> AgentResult:
        cache_key = f"{feature}:{message}"
        cached = self._response_cache.get(cache_key)
        if cached is not None:
            metrics.record_cache_hit()
            return cached

        started = time.perf_counter()
        docs = retrieve(message)
        langfuse_client = get_langfuse_client()
        prompt = resolve_prompt(
            langfuse_client,
            feature=feature,
            docs=docs,
            message=message,
            enabled=tracing_enabled(),
        )
        response = self.llm.generate(prompt.text)
        quality_score = self._heuristic_quality(message, response.text, docs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
        from structlog.contextvars import get_contextvars

        langfuse_client = get_langfuse_client()

        langfuse_client.update_current_trace(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            metadata={
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
                "prompt_source": prompt.source,
            },
        )
        langfuse_client.update_current_generation(
            model=self.model,
            metadata={
                "doc_count": len(docs),
                "query_preview": summarize_text(message),
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
                "prompt_source": prompt.source,
                "prompt_fetch_error": prompt.fetch_error,
            },
            usage_details={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            cost_details={"total": cost_usd},
            prompt=prompt.managed_prompt,
        )

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        result = AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )
        self._response_cache[cache_key] = result
        return result

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * self._pricing["input"]
        output_cost = (tokens_out / 1_000_000) * self._pricing["output"]
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
