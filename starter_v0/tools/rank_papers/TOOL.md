---
name: rank_papers
track: core
kind: local_formatter
requires_env: []
inputs: [papers, research_question, criteria, top_k]
outputs: [items, ranked_items, item_count, criteria]
side_effect: false
---
# rank_papers

Ranks an already-collected paper list against a research question using
deterministic relevance, recency, and implementation-readiness signals.

Use this tool only when paper metadata or abstracts are already available. It
does not search arXiv, read PDFs, extract paper insights, or compare papers.
