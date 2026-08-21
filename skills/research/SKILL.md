---
name: investment-research-evidence
description: Use to collect verifiable, URL-backed public evidence for one startup with Exa before analysis. Do not use for thesis scoring, recommendations, or memo writing.
---

# Investment Research / Evidence

## Purpose

Answer one question: **what verifiable public evidence exists about this
startup?**

This skill gathers facts and explicitly records unknowns. It does not score the
company, decide whether to invest, or write conclusions better suited to the
analysis stage.

## Inputs

Require a candidate record from `candidates.json` with `name` and, when known,
`website`. Accept the locked thesis only to guide relevance, not to change the
facts collected. Use the company's startup output directory.

## First research pass

Set `EXA_API_KEY`; never write it to an artifact. From the repository root,
run:

```powershell
python skills/research/scripts/research.py --name "Acme" --website "https://acme.example"
```

The helper queries Exa with `type="auto"` and highlights, then emits
URL-backed results as JSON. Use these results to collect evidence for:

- company and product;
- team and founders;
- target customer, market, and competitors;
- traction and freshness;
- funding, if public;
- technical or product signals; and
- risks and unanswered questions.

Every factual claim must have at least one source URL. Treat Exa snippets as
leads: do not convert an ambiguous snippet into a definitive claim.

## Required outputs

Write `evidence.md` with fact-only sections: `Company / Product`, `Team`,
`Market / Competitors`, `Traction / Freshness`, `Funding`, `Technical / Product
Signals`, `Risks / Unanswered Questions`, and `Unknown`.

For each factual statement, include its source URL immediately below or beside
it. Use `Not found` or `Insufficient public evidence` in `Unknown` for public
information that could not be verified.

Write `sources.json` as an array of unique provenance records:

```json
[
  {
    "url": "https://example.com/source",
    "title": "Source title",
    "retrieved_at": "2026-08-21T00:00:00Z",
    "used_for": ["team", "traction"]
  }
]
```

## Evidence-quality gate

Before handing off, mark coverage for `team`, `product`, `market`, `traction`,
`competitors`, and `freshness` as present or missing. A category is missing
when it has no credible URL-backed public evidence.

There is exactly one loop:

```text
research → evidence check → one targeted retry → final evidence
```

If one or more categories are missing after the first pass, issue one focused
Exa query for only the missing areas:

```powershell
python skills/research/scripts/research.py --name "Acme" --website "https://acme.example" --focus "traction and freshness"
```

Merge verified results into the same evidence and source artifacts. Do not run
a second broad pass or a third search. After the retry, record unresolved areas
as `Not found` or `Insufficient public evidence` and continue to analysis.

Research is the only other skill permitted to use Exa. Analysis and memo
stages must rely solely on the artifacts produced here.
