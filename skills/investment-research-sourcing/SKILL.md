---
name: investment-research-sourcing
description: Use when discovering, deduplicating, and triaging startup candidates for an initialized investment-research run.
compatibility: Requires Python 3.10+; assignment snapshots work offline; legacy Exa or web fallback requires network access
---

# Source and triage candidates

Read the run's `input.json` and `thesis.md`. Retain at most the requested count, never more than 20.

## Assignment source path

Run `scripts/search.py snapshots --input INPUT --thesis THESIS --product-hunt PRODUCT_HUNT_ATOM --yc YC_JSON --hacker-news HN_JSON --output CANDIDATES --retrieval-output RETRIEVAL`. Product Hunt and YC snapshots are required origin inputs. `--hacker-news` is optional enrichment and never creates an origin. This path reads local snapshots, requires no API key or network call, and atomically writes a current retrieval artifact plus normalized `candidates` and provenance-preserving `excluded` arrays.

Product Hunt and YC origin URLs must use their official domains. Candidate freshness or traction signals must link to one of those retained origins or an official Hacker News item. Deduplicate by canonical company domain, falling back to normalized company name only when two usable domains are unavailable.

## Legacy Exa compatibility

The legacy `scripts/search.py --input INPUT --thesis THESIS --output RETRIEVAL` form remains available for older runs. It writes the historical Exa envelope and may use native web fallback after provider failure. Do not use this legacy Exa path as the preferred assignment workflow.

## Triage contract

Write `sourcing/candidates.json` and `sourcing/retrieval.json`; do not create a prose sourcing artifact. Preserve `provider: source_snapshots`, query, retrieval path, requested and actual retained counts, `candidates`, and `excluded` from the snapshot command. Never retain more than the requested count or the hard maximum of 20.

Each retained candidate must include:

- `name`, stable `slug`, canonical `website`, and `one_line_description`;
- complete Product Hunt or YC `origins`, nullable `team_signal`, and source-linked `freshness_or_traction_signals`;
- specific `thesis_fit_reasons` and deterministic `rank`.

Each exclusion states the reason and retains its origin provenance. The snapshot command deterministically creates candidate-specific `thesis_fit_reasons` from `input.json` and `thesis.md`.

Use both atomically written artifacts as the assignment output, then mark sourcing complete with provider `source_snapshots`. Legacy Exa and web runs retain their historical provider compatibility.
