from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Iterable

from core.ai.types import AIRequest, AIResponse


@dataclass(slots=True)
class AgentResult:
    provider: str
    model: str
    response: AIResponse | None = None
    error: str | None = None


@dataclass(slots=True)
class ConsensusFinding:
    fingerprint: str
    proposition: str
    claim_element: str
    polarity: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    supporting_agents: list[str] = field(default_factory=list)
    dissenting_agents: list[str] = field(default_factory=list)
    agreement_ratio: float = 0.0
    status: str = "single_agent"
    adjudication_note: str | None = None


@dataclass(slots=True)
class MultiAgentResponse:
    task: str
    agent_results: list[AgentResult]
    findings: list[ConsensusFinding]
    consensus_level: str
    adjudicator: AgentResult | None = None
    warnings: list[str] = field(default_factory=list)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _finding_key(item: dict[str, Any]) -> str:
    proposition = _norm(item.get("proposition") or item.get("evidence_proposition") or item.get("finding"))
    element = _norm(item.get("claim_element") or item.get("element"))
    polarity = _norm(item.get("polarity") or item.get("classification"))
    source = item.get("source") or {}
    citation = f"{_norm(source.get('filename') or item.get('filename'))}:{source.get('page') or item.get('page') or ''}"
    return sha256(f"{proposition}|{element}|{polarity}|{citation}".encode()).hexdigest()[:20]


def _extract_findings(response: AIResponse) -> list[dict[str, Any]]:
    data = response.parsed
    if not isinstance(data, dict):
        try:
            data = json.loads(response.text)
        except Exception:
            return []
    for key in ("findings", "evidence", "annotations", "candidate_findings"):
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


class MultiAgentOrchestrator:
    """Runs independent providers concurrently and produces transparent consensus.

    The orchestrator never converts disagreement into fact. Findings supported by only
    one agent stay in manual review. Optional adjudication receives only the disputed
    structured findings, not the full medical record, which limits data exposure.
    """

    def __init__(self, router, providers: Iterable[str] | None = None, adjudicator: str | None = None):
        self.router = router
        self.providers = list(providers or _env_list("VCB_AI_ENSEMBLE", "openai,xai"))
        self.providers = list(dict.fromkeys(p for p in self.providers if p))
        self.adjudicator_name = adjudicator or os.getenv("VCB_AI_ADJUDICATOR") or None
        self.max_workers = max(1, int(os.getenv("VCB_AI_MAX_CONCURRENCY", str(len(self.providers) or 1))))

    def run(self, request: AIRequest, adjudicate: bool = True) -> MultiAgentResponse:
        if len(self.providers) < 2:
            raise ValueError("Multi-agent mode requires at least two configured providers")
        results: list[AgentResult] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.providers))) as pool:
            futures = {pool.submit(self.router.generate_with, name, request): name for name in self.providers}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    response = future.result()
                    results.append(AgentResult(provider=name, model=response.model, response=response))
                except Exception as exc:
                    results.append(AgentResult(provider=name, model="unknown", error=str(exc)))

        successful = [r for r in results if r.response]
        warnings = [f"{r.provider} failed: {r.error}" for r in results if r.error]
        if not successful:
            raise RuntimeError("All configured AI providers failed")

        findings = self._consensus(successful)
        adjudicator_result = None
        disputed = [f for f in findings if f.status in {"single_agent", "conflict"}]
        if adjudicate and disputed and self.adjudicator_name:
            adjudicator_result = self._adjudicate(request, disputed)
            if adjudicator_result.error:
                warnings.append(f"Adjudicator failed: {adjudicator_result.error}")
            else:
                self._apply_adjudication(findings, adjudicator_result.response)

        ratios = [f.agreement_ratio for f in findings]
        overall = "strong" if ratios and min(ratios) >= 0.75 else "mixed" if ratios and max(ratios) >= 0.5 else "limited"
        return MultiAgentResponse(request.task, results, findings, overall, adjudicator_result, warnings)

    def _consensus(self, successful: list[AgentResult]) -> list[ConsensusFinding]:
        buckets: dict[str, list[tuple[AgentResult, dict[str, Any]]]] = {}
        for agent in successful:
            for item in _extract_findings(agent.response):
                buckets.setdefault(_finding_key(item), []).append((agent, item))
        output: list[ConsensusFinding] = []
        total = len(successful)
        for key, entries in buckets.items():
            first = entries[0][1]
            supporters = sorted({a.provider for a, _ in entries})
            citations = []
            for _, item in entries:
                source = item.get("source") or {}
                citation = {
                    "filename": source.get("filename") or item.get("filename"),
                    "page": source.get("page") or item.get("page"),
                    "quote": source.get("quote") or item.get("quote"),
                }
                if citation not in citations:
                    citations.append(citation)
            ratio = len(supporters) / total
            status = "consensus" if ratio == 1 and len(supporters) >= 2 else "corroborated" if len(supporters) >= 2 and ratio >= 0.5 else "single_agent"
            output.append(ConsensusFinding(
                fingerprint=key,
                proposition=str(first.get("proposition") or first.get("evidence_proposition") or first.get("finding") or ""),
                claim_element=str(first.get("claim_element") or first.get("element") or "unknown"),
                polarity=str(first.get("polarity") or first.get("classification") or "ambiguous"),
                citations=citations,
                supporting_agents=supporters,
                dissenting_agents=sorted(set(a.provider for a in successful) - set(supporters)),
                agreement_ratio=round(ratio, 3),
                status=status,
            ))
        return sorted(output, key=lambda x: (-x.agreement_ratio, x.claim_element, x.proposition))

    def _adjudicate(self, original: AIRequest, disputed: list[ConsensusFinding]) -> AgentResult:
        payload = [{
            "fingerprint": f.fingerprint,
            "proposition": f.proposition,
            "claim_element": f.claim_element,
            "polarity": f.polarity,
            "citations": f.citations,
            "supporting_agents": f.supporting_agents,
            "dissenting_agents": f.dissenting_agents,
        } for f in disputed]
        request = AIRequest(
            task=f"{original.task}:adjudication",
            system_prompt=("Act as a conservative evidence adjudicator. Decide only whether each disputed proposition is "
                           "supported by its quoted source. Do not infer missing facts. Return JSON with decisions containing "
                           "fingerprint, decision (support/reject/manual_review), and reason."),
            user_prompt=json.dumps(payload, indent=2),
            json_schema={"type": "object", "properties": {"decisions": {"type": "array"}}},
            temperature=0.0,
            metadata={"restricted_payload": True},
        )
        try:
            response = self.router.generate_with(self.adjudicator_name, request)
            return AgentResult(self.adjudicator_name, response.model, response=response)
        except Exception as exc:
            return AgentResult(self.adjudicator_name, "unknown", error=str(exc))

    @staticmethod
    def _apply_adjudication(findings: list[ConsensusFinding], response: AIResponse | None) -> None:
        if not response or not isinstance(response.parsed, dict):
            return
        decisions = {d.get("fingerprint"): d for d in response.parsed.get("decisions", []) if isinstance(d, dict)}
        for finding in findings:
            decision = decisions.get(finding.fingerprint)
            if not decision:
                continue
            finding.adjudication_note = str(decision.get("reason") or "")
            value = decision.get("decision")
            if value == "support":
                finding.status = "adjudicated_support"
            elif value == "reject":
                finding.status = "adjudicated_reject"
            else:
                finding.status = "manual_review"


def _env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]
