from __future__ import annotations

import os

from google import genai
from google.genai import types

from .incidents import STATE
from .mock_llm import FakeResponse, FakeUsage
from .tracing import observe

DEFAULT_MODEL = "gemini-2.0-flash"

# Simulates a real-world regression (e.g. an accidental prompt/config change)
# that makes the model ramble instead of answering concisely - mirrors the
# x4 output token multiplier FakeLLM applies under the same incident.
COST_SPIKE_SUFFIX = (
    "\n\nProvide an exceptionally long, extremely detailed, and verbose answer. "
    "Cover every possible angle at length."
)


class GeminiLLM:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_PROVIDER", DEFAULT_MODEL)
        self.max_output_tokens = max_output_tokens
        self._client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))

    @observe(as_type="span")
    def generate(self, prompt: str) -> FakeResponse:
        effective_prompt = prompt
        if STATE["cost_spike"]:
            effective_prompt = prompt + COST_SPIKE_SUFFIX

        config = None
        if self.max_output_tokens:
            config = types.GenerateContentConfig(max_output_tokens=self.max_output_tokens)

        response = self._client.models.generate_content(
            model=self.model, contents=effective_prompt, config=config
        )
        usage = response.usage_metadata
        return FakeResponse(
            text=response.text or "",
            usage=FakeUsage(
                input_tokens=usage.prompt_token_count or 0,
                output_tokens=usage.candidates_token_count or 0,
            ),
            model=self.model,
        )
