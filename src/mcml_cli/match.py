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
    query: str | None,
    rows: Iterable[dict],
    *,
    first: str | None = None,
    last: str | None = None,
    limit: int = 10,
    threshold: float = 0.55,
) -> list[Match]:
    query = (query or "").strip()
    query_tokens = _norm(query).split()

    first_query = first or (query_tokens[0] if query_tokens else "")
    if last:
        last_query = last
    elif len(query_tokens) >= 2:
        last_query = query_tokens[-1]
    elif query_tokens:
        last_query = query_tokens[0]
    else:
        last_query = ""

    # Nothing useful to match against.
    if not any([query, first_query, last_query]):
        return []

    matches: list[Match] = []
    for r in rows:
        name = r.get("full_name") or ""

        full_name_score = similarity(query, name) if query else 0.0
        first_score = similarity(first_query, r.get("first_name") or "") if first_query else 0.0
        last_score = similarity(last_query, r.get("last_name") or "") if last_query else 0.0

        weighted = 0.0
        weight_total = 0.0
        if first_query:
            weighted += first_score * 0.4
            weight_total += 0.4
        if last_query:
            weighted += last_score * 0.6
            weight_total += 0.6
        combined_score = weighted / weight_total if weight_total else 0.0

        n_last = _norm(r.get("last_name") or "")
        n_first = _norm(r.get("first_name") or "")
        boost = 0.0
        if last_query and n_last and _norm(last_query) == n_last:
            boost += 0.15
        if first_query and n_first and _norm(first_query) == n_first:
            boost += 0.05

        score = max(full_name_score, first_score, last_score, combined_score) + boost
        score = min(score, 1.0)

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
