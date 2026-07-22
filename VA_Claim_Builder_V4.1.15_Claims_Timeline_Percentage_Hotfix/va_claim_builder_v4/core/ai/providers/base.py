from __future__ import annotations
from abc import ABC, abstractmethod
from core.ai.types import AIRequest, AIResponse

class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def health_check(self) -> tuple[bool, str]: ...

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse: ...
