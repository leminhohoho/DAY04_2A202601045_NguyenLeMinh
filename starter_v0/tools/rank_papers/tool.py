from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from tools._shared import err, fold_text, terms


IMPLEMENTATION_SIGNALS = {
    "benchmark",
    "code",
    "dataset",
    "deployment",
    "empirical",
    "evaluation",
    "experiment",
    "framework",
    "github",
    "implementation",
    "open source",
    "reproducible",
    "system",
    "thuc nghiem",
    "trien khai",
}


def _paper_year(paper: dict[str, Any]) -> int | None:
    for field in ("year", "published", "updated", "date"):
        value = paper.get(field)
        if isinstance(value, int):
            return value
        match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
        if match:
            return int(match.group(0))
    return None


def _paper_text(paper: dict[str, Any]) -> str:
    categories = paper.get("categories") or []
    if not isinstance(categories, list):
        categories = [categories]
    return " ".join([
        str(paper.get("title") or ""),
        str(paper.get("summary") or ""),
        str(paper.get("abstract") or ""),
        str(paper.get("primary_category") or ""),
        " ".join(str(value) for value in categories),
    ])


def _relevance_score(paper: dict[str, Any], query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    title_terms = terms(str(paper.get("title") or ""))
    body_terms = terms(_paper_text(paper))
    title_coverage = len(query_terms & title_terms) / len(query_terms)
    body_coverage = len(query_terms & body_terms) / len(query_terms)
    return min(1.0, 0.35 * title_coverage + 0.65 * body_coverage)


def _recency_score(year: int | None) -> float:
    if year is None:
        return 0.0
    age = max(0, datetime.now().year - year)
    return max(0.0, 1.0 - age / 10)


def _implementation_score(paper: dict[str, Any]) -> tuple[float, list[str]]:
    text = fold_text(_paper_text(paper))
    matched = sorted(signal for signal in IMPLEMENTATION_SIGNALS if signal in text)
    return min(1.0, len(matched) / 4), matched


def _score_for(criteria: str, relevance: float, recency: float, implementation: float) -> float:
    if criteria == "relevance":
        return relevance
    if criteria == "recency":
        return recency
    if criteria == "implementation":
        return implementation
    return 0.6 * relevance + 0.2 * recency + 0.2 * implementation


def _ranking_reason(
    *,
    relevance: float,
    recency: float,
    implementation: float,
    signals: list[str],
) -> str:
    reasons: list[str] = []
    if relevance >= 0.7:
        reasons.append("high research-question relevance")
    elif relevance >= 0.35:
        reasons.append("partial research-question relevance")
    else:
        reasons.append("limited keyword relevance")
    if recency >= 0.8:
        reasons.append("recent publication")
    if implementation >= 0.5:
        preview = ", ".join(signals[:3])
        reasons.append(f"implementation evidence: {preview}")
    return "; ".join(reasons)


def rank_papers(
    papers: list[dict[str, Any]] | None = None,
    research_question: str = "",
    criteria: str = "balanced",
    top_k: int = 5,
) -> dict[str, Any]:
    try:
        criteria = (criteria or "balanced").strip().lower()
        if criteria not in {"relevance", "recency", "implementation", "balanced"}:
            raise ValueError("criteria must be relevance, recency, implementation, or balanced")
        if not str(research_question or "").strip():
            raise ValueError("research_question is required")

        source_items = [dict(item) for item in (papers or []) if isinstance(item, dict)]
        requested_top_k = max(1, int(top_k or 5))
        query_terms = terms(research_question)
        scored: list[dict[str, Any]] = []

        for paper in source_items:
            year = _paper_year(paper)
            relevance = _relevance_score(paper, query_terms)
            recency = _recency_score(year)
            implementation, signals = _implementation_score(paper)
            final_score = _score_for(criteria, relevance, recency, implementation)
            ranked_paper = {
                **paper,
                "score": round(final_score, 4),
                "relevance_score": round(relevance, 4),
                "recency_score": round(recency, 4),
                "implementation_score": round(implementation, 4),
                "ranking_reason": _ranking_reason(
                    relevance=relevance,
                    recency=recency,
                    implementation=implementation,
                    signals=signals,
                ),
            }
            scored.append(ranked_paper)

        scored.sort(
            key=lambda item: (
                -float(item["score"]),
                -int(_paper_year(item) or 0),
                str(item.get("title") or "").casefold(),
            )
        )
        ranked_items = scored[:requested_top_k]
        for index, item in enumerate(ranked_items, start=1):
            item["rank"] = index

        return {
            "tool": "rank_papers",
            "research_question": research_question,
            "criteria": criteria,
            "top_k": requested_top_k,
            "items": ranked_items,
            "ranked_items": ranked_items,
            "input_count": len(source_items),
            "item_count": len(ranked_items),
        }
    except Exception as exc:
        return err("rank_papers", exc)
