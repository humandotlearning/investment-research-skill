---
name: investment-research-analysis
description: Use when public evidence for a startup has been collected and a locked investment thesis is available, and an evidence-bound investment analysis and score are needed. Do not use for sourcing, web research, or memo writing.
---

# Investment Research Analysis

## Purpose and boundary

Turn supplied, URL-backed evidence into an investment assessment. **Do not
browse the web, call Exa, run a search, or add facts from prior knowledge.**
Only the sourcing and research stages may retrieve information. A missing
signal is an evidence gap, not evidence that the company is weak.

## Inputs and artifact compatibility

Require explicit paths to the locked `thesis.md`, a candidate record,
`evidence.md`, and `sources.json`. Do not infer paths, move files, or modify
the input artifacts.

Accept either layout:

```text
Current:   runs/<run-id>/evidence/<slug>/evidence.md
           → runs/<run-id>/analysis/<slug>/analysis.md

Preferred: artifacts/<run-id>/startups/<slug>/evidence.md
           → artifacts/<run-id>/startups/<slug>/analysis.md
```

Write to the explicit `analysis.md` output path supplied by the orchestrator.

## Method

1. Read the thesis first and treat it as locked. Extract any stated musts,
   preferences, avoids, score weights, and recommendation thresholds.
2. Read the evidence and source inventory. Separate each conclusion into:
   supported inference, evidence gap, or open question. Refer back to the
   relevant evidence section and source URL for every factual premise.
3. Apply the thesis rubric. If it does not define a replacement, score five
   categories from 0–20: Team, Product differentiation, Market
   attractiveness, Traction, and Thesis alignment. Do not award points for a
   claim that is absent or unverified.
4. Total the five category scores exactly. The final score is their arithmetic
   sum out of 100. State a recommendation basis from the thesis; if none is
   supplied, use `80–100: Take a meeting`, `65–79: Watch`, and `0–64: Pass`.
   This is an analysis result for the memo to preserve, not a prompt to seek
   additional evidence.

## Required `analysis.md` shape

```markdown
# <Company> — Investment Analysis

## Thesis fit
<How the company matches or conflicts with the locked thesis.>

## Team
## Product
## Market and why now
## Competition
## Traction
## Risks and evidence gaps
## Open questions

## Scorecard
| Category | Score / 20 | Evidence and reasoning |
| --- | ---: | --- |
| Team | | |
| Product differentiation | | |
| Market attractiveness | | |
| Traction | | |
| Thesis alignment | | |
| **Final score** | **<sum> / 100** | **Arithmetic total** |

## Recommendation basis
<Pass, Watch, or Take a meeting, using the stated threshold.>
```

Use `Not found` or `Insufficient public evidence` for unresolved information.
Do not disguise an inference as a fact, treat silence as a negative claim, or
make a recommendation that contradicts the score threshold without stating the
thesis-defined exception and its evidence.

## Handoff

Pass the explicit analysis path with the evidence and source paths to the memo
stage. The memo may improve presentation but must not browse, change the score,
or materially reconsider this assessment.
