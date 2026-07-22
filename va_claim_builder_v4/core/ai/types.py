from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

ProviderName = Literal["openai", "xai", "local"]

@dataclass(slots=True)
class AIRequest:
    task: str
    system_prompt: str
    user_prompt: str
    json_schema: dict[str, Any] | None = None
    temperature: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class AIResponse:
    provider: ProviderName
    model: str
    text: str
    parsed: dict[str, Any] | None
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    raw: Any = None
