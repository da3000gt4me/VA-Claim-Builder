from __future__ import annotations
import json, os
import httpx
from core.ai.providers.base import AIProvider
from core.ai.types import AIRequest, AIResponse

class XAIProvider(AIProvider):
    name = "xai"

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("VCB_XAI_MODEL", "grok-4.5")
        self.api_key = os.getenv("XAI_API_KEY")
        self.base_url = "https://api.x.ai/v1"

    def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "XAI_API_KEY is not configured"
        return True, f"xAI configured with {self.model}"

    def generate(self, request: AIRequest) -> AIResponse:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
        }
        with httpx.Client(timeout=180) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_fence(text)) if request.json_schema else None
        usage = data.get("usage", {})
        return AIResponse(
            provider="xai", model=self.model, text=text, parsed=parsed,
            request_id=data.get("id"), input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"), raw=data,
        )

def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip()
