from __future__ import annotations
import json, os
from openai import OpenAI
from core.ai.providers.base import AIProvider
from core.ai.types import AIRequest, AIResponse

class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("VCB_OPENAI_MODEL", "gpt-5")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def health_check(self) -> tuple[bool, str]:
        if not os.getenv("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY is not configured"
        return True, f"OpenAI configured with {self.model}"

    def generate(self, request: AIRequest) -> AIResponse:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        # Keep broad SDK compatibility. The prompt requires JSON when a schema is supplied.
        response = self.client.responses.create(**payload)
        text = response.output_text
        parsed = None
        if request.json_schema:
            parsed = json.loads(_strip_fence(text))
        usage = getattr(response, "usage", None)
        return AIResponse(
            provider="openai", model=self.model, text=text, parsed=parsed,
            request_id=getattr(response, "id", None),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            raw=response,
        )

def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip()
