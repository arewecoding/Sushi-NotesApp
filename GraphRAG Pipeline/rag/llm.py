"""
llm.py — LLM integration for final answer synthesis.

Uses Google Gemini API for generating answers from assembled context.
"""

import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from .context import AssembledContext
from .schema import HyperParams, RAGConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from the LLM."""

    answer: str
    model: str
    usage: dict  # token counts


class LLMClient:
    """
    LLM client using Google Gemini API for answer synthesis.
    """

    def __init__(self, config: RAGConfig, hp: HyperParams | None = None):
        self.config = config
        self.hp = hp or HyperParams()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.config.google_api_key)
        return self._client

    def synthesize(
        self, context: AssembledContext, system_prompt: str | None = None
    ) -> LLMResponse:
        """
        Generate a final answer from the assembled context.

        Args:
            context:       The assembled context (includes query + retrieved blocks)
            system_prompt: Optional system prompt override

        Returns:
            LLMResponse with the generated answer
        """
        if system_prompt is None:
            system_prompt = (
                "You are a knowledgeable assistant helping a user with their personal notes. "
                "Answer questions based on the provided note excerpts. Be concise, accurate, "
                "and cite the source notes when possible. If the notes don't fully address "
                "the question, clearly state what's missing."
            )

        try:
            response = self.client.models.generate_content(
                model=self.config.llm_model,
                contents=context.context_text,
                config=types.GenerateContentConfig(
                    temperature=self.hp.synthesis_temperature,
                    system_instruction=system_prompt,
                ),
            )

            answer = response.text or ""
            usage = {}
            if response.usage_metadata:
                usage = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count,
                }

            return LLMResponse(
                answer=answer,
                model=self.config.llm_model,
                usage=usage,
            )

        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return LLMResponse(
                answer=f"Error generating response: {e}",
                model=self.config.llm_model,
                usage={},
            )
