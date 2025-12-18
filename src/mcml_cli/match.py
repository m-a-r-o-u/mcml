from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def similarity(a: str, b: str) -> float:
    a_n = _norm(a)
    b_n = _norm(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(None, a_n, b_n).ratio()


@dataclass(frozen=True)
class Match:
    score: float
    full_name: str
    role: str
    note: str
    mcml_url: str
    source_page: str


def find_best_matches(
    query: str,
    rows: Iterable[dict],
    limit: int = 10,
    threshold: float = 0.55,
) -> list[Match]:
    matches: list[Match] = []
    for r in rows:
        name = r.get("full_name") or ""
        score = similarity(query, name)
        # Small boost if last name token matches exactly.
        q_last = _norm(query).split(" ")[-1] if _norm(query) else ""
        n_last = _norm(name).split(" ")[-1] if _norm(name) else ""
        if q_last and n_last and q_last == n_last:
            score = min(1.0, score + 0.15)
        if score >= threshold:
            matches.append(
                Match(
                    score=score,
                    full_name=name,
                    role=r.get("role") or "",
                    note=r.get("note") or "",
                    mcml_url=r.get("mcml_url") or "",
                    source_page=r.get("source_page") or "",
                )
            )

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
