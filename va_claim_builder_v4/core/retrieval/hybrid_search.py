from __future__ import annotations
import math, re
from collections import Counter
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-/]{1,}")

def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]

def lexical_score(query: str, text: str) -> float:
    q, d = Counter(tokens(query)), Counter(tokens(text))
    if not q or not d: return 0.0
    dot = sum(q[k] * d.get(k, 0) for k in q)
    qn = math.sqrt(sum(v*v for v in q.values())); dn = math.sqrt(sum(v*v for v in d.values()))
    return dot / (qn * dn) if qn and dn else 0.0

class ClaimRetriever:
    """Local claim-specific retrieval. Keeps full records on-device."""
    def __init__(self, db): self.db = db

    def retrieve(self, project_id: str, claim_id: str, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        claim = next((c for c in self.db.list_claims(project_id) if c["id"] == claim_id), None)
        if not claim: raise KeyError(claim_id)
        search_text = " ".join(x for x in [claim["condition_name"], claim.get("theory", ""), query] if x)
        rows = self.db.list_chunks(project_id, claim_id=claim_id)
        for row in rows:
            row["retrieval_score"] = lexical_score(search_text, row.get("text", ""))
        rows.sort(key=lambda r: (r["retrieval_score"], r.get("ocr_confidence") or 0), reverse=True)
        return rows[:limit]
