# Investment Analysis and Memo Skills Design

## Goal

Add two bounded downstream skills for the investment-research pipeline: one to reason from collected evidence and one to turn that reasoning into a partner-facing memo.

## Scope

- Create `skills/analysis/SKILL.md` and `skills/memo/SKILL.md`.
- Do not change the existing `start`, `sourcing`, or `research` skills.
- Support both the current run layout and the proposed consolidated startup layout.

## Compatibility contract

The skills accept explicit artifact paths. For a company slug, accepted inputs and outputs are either:

```text
Current: runs/<run-id>/evidence/<slug>/evidence.md
         runs/<run-id>/analysis/<slug>/analysis.md
         runs/<run-id>/memos/<slug>/memo.md

Preferred: artifacts/<run-id>/startups/<slug>/evidence.md
           artifacts/<run-id>/startups/<slug>/analysis.md
           artifacts/<run-id>/startups/<slug>/memo.md
```

`thesis.md` remains a run-level input in either layout. The skills must not infer a location or move artifacts: the orchestrator passes the paths explicitly.

## Analysis skill

Analysis reads the locked thesis and evidence only. It must not browse, call Exa, or introduce facts beyond the evidence and its cited sources. It produces a structured `analysis.md` with team, product, market, why now, competition, risks, evidence gaps, open questions, score breakdown, final score, and recommendation context.

The score is a five-category rubric worth 20 points each: team, product differentiation, market attractiveness, traction, and thesis alignment. Each category must state evidence, reasoning, score, and the impact of missing evidence. The final score is the arithmetic total and cannot be compensated by invented evidence.

## Memo skill

Memo reads the candidate record, evidence, analysis, and sources only. It must not browse, alter scores, or substantively revise the investment case. It produces a concise one-page `memo.md` containing company, one-line description, recommendation, why, what we like, concerns, score, what would change our mind, and selected sources.

Recommendation is exactly one of `Pass`, `Watch`, or `Take a meeting`; it must be consistent with the analysis and disclose material evidence gaps.

## Validation

Before each skill is written, confirm the expected skill file does not exist. After authoring, run the bundled skill validator and inspect the document against representative evidence scenarios, including unavailable traction and missing founder information.
