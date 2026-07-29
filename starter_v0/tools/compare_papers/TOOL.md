---
name: compare_papers
track: core
kind: local_formatter
requires_env: []
inputs: [papers, dimensions, max_papers]
outputs: [comparison_rows, markdown, common_terms, distinctive_terms, warnings]
side_effect: false
---
# compare_papers

Builds a structured and Markdown comparison of two or more already-collected
papers using metadata, abstracts, ranking scores, and optional extracted
insights.

It does not search arXiv, download PDFs, rank papers, or invent unavailable
method/result/limitation claims.
