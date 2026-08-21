---
name: investment-research-start
description: Use when running an AI-augmented investment research pipeline from a topic query, URL list, or public startup feed and coordinating sourcing, evidence, analysis, and memo stages.
---

# Investment Research Start

## Purpose

Act as the workflow coordinator for an investment-triage run. Establish the run, validate the seed input, preserve the thesis, and hand work to the stage skills in order. This skill does not perform web research, startup analysis, or memo writing itself.

The operating boundary is:

```text
input → sourcing → research/evidence → analysis → memo → run summary
```

Research produces evidence. Analysis consumes evidence. Memo generation consumes analysis. Keep those boundaries intact so every run is replayable and claims remain traceable.

## Inputs

Accept one seed input:

- a topic query, such as `AI agents for SMBs`;
- a list of startup or source URLs; or
- a public feed or batch, such as a YC batch.

Accept an optional thesis. If it is missing, define a specific, defensible thesis from the request before invoking downstream stages. Record the thesis and any assumptions; do not silently substitute a broad quality judgment such as “good companies.”

Reject an empty, private, or otherwise unusable seed before creating downstream artifacts. If the input is ambiguous but a reasonable interpretation is safe, record the interpretation in `input.json` and continue.

## Run setup

Create a unique run directory before calling another stage:

```text
runs/<run-id>/
├── input.json
├── thesis.md
├── candidates.json
├── evidence/<company-slug>/evidence.md
├── analysis/<company-slug>/analysis.md
├── memos/<company-slug>/memo.md
└── run-summary.md
```

Use a stable, human-readable run ID containing the date and a slug. Keep normalized input, the exact thesis, assumptions, source/query references, and stage status in the run directory. Never overwrite an existing run; resume it only when its artifacts and inputs match.

## Stage contracts

Invoke the stage skills in this order:

1. **Sourcing** receives `input.json` and `thesis.md`. It may use Exa, normalizes and deduplicates 10–20 candidates, and writes `candidates.json` with each candidate’s name, website, plain-language description, team signal, freshness or traction signal, and source URLs.
2. **Research** receives one candidate plus the thesis. It may use Exa and writes `evidence/<company-slug>/evidence.md`, covering team, product, market, traction, risks, and source URLs. It must distinguish sourced facts, inference, and unavailable information, and preserve the queries or references used.
3. **Analysis** receives the thesis, candidate list, and evidence artifacts. It does not browse. It writes `analysis/<company-slug>/analysis.md` with team, product, market, risks/open questions, evidence gaps, and a 0–100 thesis score.
4. **Memo** receives the candidate, evidence, and analysis. It does not browse. It writes a skimmable one-page `memos/<company-slug>/memo.md` ending in exactly one call: `Pass`, `Watch`, or `Take a meeting`, plus rationale and 2–3 things that could change the call.
5. Write `run-summary.md` with the run ID, thesis, candidate count, completed/failed stages, evidence gaps, calls, and any assumptions or retries.

Pass artifact paths explicitly between stages. If a required stage skill or artifact is missing, stop and report the dependency; do not absorb that stage’s work into this orchestrator.

## Evidence gate

There is one controlled loop per candidate:

```text
research → evidence check → one targeted research retry if needed
```

Treat evidence as insufficient when a required area has no credible public source, a claim cannot be traced to a URL, or the result is only generic search text. The retry must target the missing area. After one retry, continue with `Not found` or `Insufficient public evidence`, record the gap in the analysis and memo, and never search indefinitely.

Analysis and memo stages must not invent facts to fill evidence gaps. A missing signal is a disclosed uncertainty, not a negative fact.

## Completion checklist

Before declaring the run complete, verify:

- the thesis is specific and present in the run artifacts;
- candidates are normalized, deduplicated, and source-linked;
- every company has evidence, analysis, and a memo or an explicit failure record;
- analysis and memo artifacts contain no unsupported factual claims;
- every memo has one clear call and 2–3 mind-changing questions;
- `run-summary.md` reports missing data, retry count, and partial failures.
