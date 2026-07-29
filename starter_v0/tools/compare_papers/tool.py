from __future__ import annotations

import re
from typing import Any

from tools._shared import err, fold_text, terms


DEFAULT_DIMENSIONS = ["research_focus", "method", "dataset", "results", "limitations"]
ALLOWED_DIMENSIONS = {
    "research_focus",
    "method",
    "dataset",
    "results",
    "limitations",
    "implementation",
    "relevance",
}

DIMENSION_LABELS = {
    "research_focus": "Research focus",
    "method": "Method",
    "dataset": "Dataset",
    "results": "Results",
    "limitations": "Limitations",
    "implementation": "Implementation",
    "relevance": "Relevance",
}

DIMENSION_MARKERS = {
    "method": ("we propose", "we introduce", "method", "approach", "framework", "architecture", "model"),
    "dataset": ("dataset", "corpus", "benchmark", "training data", "test set", "evaluation set"),
    "results": ("result", "outperform", "improve", "achieve", "accuracy", "performance", "evaluation"),
    "limitations": ("limitation", "limited by", "future work", "does not", "cannot", "however"),
    "implementation": ("implementation", "source code", "github", "runtime", "latency", "deployment", "reproduc"),
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


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
    insights = paper.get("insights") or {}
    insight_text = " ".join(str(value) for value in insights.values()) if isinstance(insights, dict) else ""
    return " ".join([
        str(paper.get("title") or ""),
        str(paper.get("summary") or ""),
        str(paper.get("abstract") or ""),
        insight_text,
    ])


def _sentences(value: str) -> list[str]:
    compact = re.sub(r"\s+", " ", value).strip()
    if not compact:
        return []
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
        if len(part.strip()) >= 25
    ]


def _insight_value(paper: dict[str, Any], key: str) -> str:
    insights = paper.get("insights")
    if isinstance(insights, dict) and str(insights.get(key) or "").strip():
        return str(insights[key]).strip()
    return str(paper.get(key) or "").strip()


def _matching_sentence(paper: dict[str, Any], dimension: str) -> str:
    markers = DIMENSION_MARKERS.get(dimension, ())
    for sentence in _sentences(_paper_text(paper)):
        folded = fold_text(sentence)
        if any(marker in folded for marker in markers):
            return sentence
    return ""


def _dimension_value(paper: dict[str, Any], dimension: str) -> str:
    if dimension == "research_focus":
        direct = _insight_value(paper, "problem")
        if direct:
            return direct
        sentences = _sentences(str(paper.get("summary") or paper.get("abstract") or ""))
        return sentences[0] if sentences else ""
    if dimension == "implementation":
        direct = _insight_value(paper, "implementation_notes")
        if direct:
            return direct
        ranking_reason = str(paper.get("ranking_reason") or "").strip()
        return ranking_reason or _matching_sentence(paper, dimension)
    if dimension == "relevance":
        score = paper.get("relevance_score", paper.get("score"))
        reason = str(paper.get("ranking_reason") or "").strip()
        if score is not None and reason:
            return f"score={score}; {reason}"
        if score is not None:
            return f"score={score}"
        return reason
    direct = _insight_value(paper, dimension)
    return direct or _matching_sentence(paper, dimension)


def _authors_text(value: Any) -> str:
    authors = [str(item).strip() for item in _as_list(value) if str(item).strip()]
    return ", ".join(authors) if authors else "Unknown"


def _clean_cell(value: Any, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).replace("|", "\\|").strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text or "Not available in provided metadata"


def _markdown_table(rows: list[dict[str, Any]], dimensions: list[str]) -> str:
    headers = ["Paper", "Year", *[DIMENSION_LABELS[item] for item in dimensions]]
    separator = ["---"] * len(headers)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in rows:
        values = [
            _clean_cell(row.get("title")),
            _clean_cell(row.get("year")),
            *[_clean_cell(row.get(dimension)) for dimension in dimensions],
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _term_analysis(papers: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[str]]]:
    term_sets = [terms(_paper_text(paper)) for paper in papers]
    common = set.intersection(*term_sets) if term_sets else set()
    common_terms = sorted(common)[:12]
    distinctive: dict[str, list[str]] = {}
    for index, (paper, paper_terms) in enumerate(zip(papers, term_sets), start=1):
        other_terms: set[str] = set()
        for other_index, values in enumerate(term_sets):
            if other_index != index - 1:
                other_terms.update(values)
        title = str(paper.get("title") or f"Paper {index}")
        distinctive[title] = sorted(paper_terms - other_terms)[:10]
    return common_terms, distinctive


def compare_papers(
    papers: list[dict[str, Any]] | None = None,
    dimensions: list[str] | None = None,
    max_papers: int = 5,
) -> dict[str, Any]:
    try:
        source_items = [dict(item) for item in (papers or []) if isinstance(item, dict)]
        if len(source_items) < 2:
            raise ValueError("compare_papers requires at least two papers")
        limit = max(2, min(int(max_papers or 5), 10))
        selected = source_items[:limit]

        requested_dimensions = [
            str(item).strip().lower()
            for item in (dimensions or DEFAULT_DIMENSIONS)
            if str(item).strip()
        ]
        invalid = [item for item in requested_dimensions if item not in ALLOWED_DIMENSIONS]
        if invalid:
            raise ValueError(f"Unsupported comparison dimensions: {', '.join(invalid)}")
        requested_dimensions = list(dict.fromkeys(requested_dimensions))

        warnings: list[str] = []
        rows: list[dict[str, Any]] = []
        for index, paper in enumerate(selected, start=1):
            title = str(paper.get("title") or f"Paper {index}").strip()
            row: dict[str, Any] = {
                "title": title,
                "year": _paper_year(paper) or "Unknown",
                "authors": _authors_text(paper.get("authors")),
                "arxiv_id": str(paper.get("arxiv_id") or ""),
                "url": str(paper.get("url") or ""),
            }
            for dimension in requested_dimensions:
                value = _dimension_value(paper, dimension)
                row[dimension] = value
                if not value:
                    warnings.append(f"{title}: {dimension} not available in provided metadata")
            rows.append(row)

        common_terms, distinctive_terms = _term_analysis(selected)
        newest = max(selected, key=lambda item: _paper_year(item) or 0)
        ranked_candidates = [item for item in selected if item.get("rank") is not None or item.get("score") is not None]
        highest_ranked = (
            min(ranked_candidates, key=lambda item: int(item.get("rank") or 10**9))
            if any(item.get("rank") is not None for item in ranked_candidates)
            else max(ranked_candidates, key=lambda item: float(item.get("score") or 0))
            if ranked_candidates
            else None
        )

        return {
            "tool": "compare_papers",
            "dimensions": requested_dimensions,
            "input_count": len(source_items),
            "item_count": len(rows),
            "comparison_rows": rows,
            "markdown": _markdown_table(rows, requested_dimensions),
            "common_terms": common_terms,
            "distinctive_terms": distinctive_terms,
            "highlights": {
                "newest_paper": str(newest.get("title") or ""),
                "highest_ranked_paper": str(highest_ranked.get("title") or "") if highest_ranked else None,
            },
            "warnings": warnings,
            "trust_boundary": "Comparison uses only provided metadata and extractive insights; unavailable claims are left missing.",
        }
    except Exception as exc:
        return err("compare_papers", exc)
