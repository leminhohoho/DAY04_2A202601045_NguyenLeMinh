---
name: extract_paper_insights
track: core
kind: local_formatter
requires_env: []
inputs: [text, txt_path, title, focus, max_sentences_per_section, max_chars]
outputs: [insights, evidence_snippets, missing_sections, source_type, chars_read]
side_effect: false
---
# extract_paper_insights

Extracts evidence-backed problem, method, dataset, result, limitation, and
implementation snippets from paper text.

Prefer `txt_path` returned by `paper_text`; direct `text` is also supported.
Local paths are restricted to `starter_v0/arxiv_papers/*.txt`. The tool is
extractive: it does not search arXiv, rank papers, compare papers, or invent
missing claims.
