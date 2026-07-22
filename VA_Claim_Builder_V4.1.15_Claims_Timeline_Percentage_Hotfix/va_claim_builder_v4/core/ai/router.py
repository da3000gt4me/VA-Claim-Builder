from __future__ import annotations
import os
from tenacity import retry, stop_after_attempt, wait_exponential
from core.ai.providers.base import AIProvider
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.xai_provider import XAIProvider
from core.ai.types import AIRequest, AIResponse

class AIRouter:
    """Provider-neutral gateway with fallback and local-only enforcement."""
    def __init__(self, primary: str | None = None, fallback: str | None = None):
        self.primary_name = primary or os.getenv("VCB_AI_PROVIDER", "openai")
        self.fallback_name = fallback
        self.local_only = os.getenv("VCB_LOCAL_ONLY", "false").lower() == "true"

    def _provider(self, name: str) -> AIProvider:
        if self.local_only and name != "local":
            raise RuntimeError("Cloud AI is disabled by VCB_LOCAL_ONLY=true")
        if name == "openai": return OpenAIProvider()
        if name == "xai": return XAIProvider()
        raise ValueError(f"Unsupported provider: {name}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _call(self, provider: AIProvider, request: AIRequest) -> AIResponse:
        ok, message = provider.health_check()
        if not ok: raise RuntimeError(message)
        return provider.generate(request)

    def generate_with(self, provider_name: str, request: AIRequest) -> AIResponse:
        """Call one named provider without fallback; used for independent ensemble analysis."""
        return self._call(self._provider(provider_name), request)

    def generate(self, request: AIRequest) -> AIResponse:
        try:
            return self._call(self._provider(self.primary_name), request)
        except Exception:
            if not self.fallback_name or self.fallback_name == self.primary_name:
                raise
            return self._call(self._provider(self.fallback_name), request)
