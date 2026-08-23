---
name: investment-research-sourcing
description: Use when discovering, deduplicating, and triaging startup candidates for an initialized investment-research run.
compatibility: Requires Python 3.10+ and network access for Exa or agent-native web search
---

# Source and triage candidates

Read the run's `input.json` and `thesis.md`. Retrieve at most the requested count, never more than 20.

## Retrieval

Prefer `scripts/search.py --input INPUT --thesis THESIS --output RETRIEVAL`. It writes a compact atomic Exa envelope and prints only status. If it fails, preserve that envelope, use native web search when available, and create the same envelope shape with `provider: web`, query, retrieval time, status, exit code, optional bounded error/stderr, and results.

For every result, keep the canonical URL, title, publication date when available, and at most one 400-character highlight. Deduplicate canonical URLs.

## Triage contract

Write only `sourcing/candidates.json`; do not create a prose sourcing artifact. Include provider/query metadata, requested and actual retained counts, `candidates`, and `excluded`.

Each retained candidate must include:

- `name`, stable `slug`, canonical `website`, and `candidate_type` as `priority` or `comparable`;
- specific `fit_reasons`, numeric `research_priority`, `source_quality`, and `source_urls`;
- `selected_for_research`, true for the highest-ranked priority candidates up to the research limit.

Each exclusion uses `candidate_type: excluded` and states the reason. Keep useful comparables, but do not deeply research them unless `input.json` explicitly sets `research.full_coverage` to true.

Commit both JSON artifacts atomically, then mark sourcing completed through the entry-point run helper.
