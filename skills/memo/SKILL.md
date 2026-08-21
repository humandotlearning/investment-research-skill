---
name: investment-research-memo
description: Use when a startup has an evidence artifact and completed investment analysis, and a concise partner-facing investment memo is needed. Do not use for sourcing, public research, scoring, or reconsidering the thesis.
---

# Investment Research Memo

## Purpose and boundary

Convert supplied evidence and analysis into a skimmable, one-page
partner-facing memo. **Do not browse, call Exa, search, change the score, or
substantively reconsider the thesis.** This stage presents the decision already
made in analysis; it does not manufacture a better-supported case.

## Inputs and artifact compatibility

Require explicit paths to the candidate record, locked `thesis.md`,
`evidence.md`, `sources.json`, and completed `analysis.md`. Do not infer paths,
move files, or modify upstream artifacts.

Accept either layout:

```text
Current:   runs/<run-id>/evidence/<slug>/evidence.md
           runs/<run-id>/analysis/<slug>/analysis.md
           → runs/<run-id>/memos/<slug>/memo.md

Preferred: artifacts/<run-id>/startups/<slug>/evidence.md
           artifacts/<run-id>/startups/<slug>/analysis.md
           → artifacts/<run-id>/startups/<slug>/memo.md
```

Write to the explicit `memo.md` output path supplied by the orchestrator.

## Method

1. Treat `analysis.md` as authoritative for the score, thesis fit, concerns,
   and recommendation basis. Copy its final score exactly; never recalculate
   it. Use its recommendation unless the analysis explicitly records a
   thesis-defined exception.
2. Use `evidence.md` and `sources.json` only to make the summary traceable.
   Every factual statement must already appear in those artifacts. Prefer the
   clearest, decision-relevant facts and preserve material uncertainty.
3. Select exactly one recommendation: `Pass`, `Watch`, or `Take a meeting`.
   Do not hedge with multiple calls. If analysis lacks a score or recommendation
   basis, stop and return the missing-artifact dependency instead of inventing a
   conclusion.

## Required `memo.md` shape

```markdown
# <Company>

## One-line description
<One sourced sentence describing the company and product.>

## Recommendation
**<Pass | Watch | Take a meeting>**

## Why
- <2–3 analysis-backed reasons>

## What we like
- <Specific evidence-backed strength>

## Concerns
- <Specific risk, gap, or unanswered question>

## Score
**<exact analysis final score> / 100**

## What would change our mind?
1. <A concrete fact, customer reference, metric, or answer that would change the call.>
2. <A second concrete decision-changing item.>
3. <Optional third item.>

## Sources
- [<title>](<URL>) — <what this source supports>
```

Keep the memo to roughly one page: state the decision early, use concise
bullets, and select rather than repeat evidence. Include a material public-data
gap explicitly as `Not found` or `Insufficient public evidence`; do not quietly
remove it to make the memo cleaner.

## Handoff

Return the explicit memo path to the start/orchestration stage for inclusion in
the run summary. If the orchestrator creates a portfolio summary, it may use
the company name, copied score, and exact recommendation from this memo without
performing new research.
