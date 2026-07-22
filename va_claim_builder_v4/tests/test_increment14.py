from core.ai.multi_agent import MultiAgentOrchestrator
from core.ai.types import AIRequest, AIResponse


class FakeRouter:
    def __init__(self, payloads):
        self.payloads = payloads

    def generate_with(self, provider, request):
        value = self.payloads[provider]
        if isinstance(value, Exception):
            raise value
        return AIResponse(provider=provider, model=f"{provider}-model", text="", parsed=value)


def request():
    return AIRequest(task="test", system_prompt="s", user_prompt="u")


def finding(text="Diagnosis documented"):
    return {"findings": [{"proposition": text, "claim_element": "current_diagnosis", "polarity": "favorable", "source": {"filename": "a.pdf", "page": 3, "quote": "diagnosed"}}]}


def test_parallel_consensus():
    router = FakeRouter({"openai": finding(), "xai": finding()})
    result = MultiAgentOrchestrator(router, ["openai", "xai"]).run(request(), adjudicate=False)
    assert result.consensus_level == "strong"
    assert result.findings[0].status == "consensus"
    assert set(result.findings[0].supporting_agents) == {"openai", "xai"}


def test_single_agent_stays_reviewable():
    router = FakeRouter({"openai": finding(), "xai": {"findings": []}})
    result = MultiAgentOrchestrator(router, ["openai", "xai"]).run(request(), adjudicate=False)
    assert result.findings[0].status == "single_agent"
    assert result.findings[0].agreement_ratio == 0.5


def test_provider_failure_is_visible():
    router = FakeRouter({"openai": finding(), "xai": RuntimeError("offline")})
    result = MultiAgentOrchestrator(router, ["openai", "xai"]).run(request(), adjudicate=False)
    assert result.warnings
    assert result.findings[0].status == "single_agent"  # one surviving agent cannot establish corroboration


def test_duplicate_provider_names_removed():
    router = FakeRouter({"openai": finding(), "xai": finding()})
    obj = MultiAgentOrchestrator(router, ["openai", "openai", "xai"])
    assert obj.providers == ["openai", "xai"]
