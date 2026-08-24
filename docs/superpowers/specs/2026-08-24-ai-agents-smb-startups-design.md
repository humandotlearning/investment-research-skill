# AI Agents for SMB Startups — Investment Research Design

## Objective

Run an evidence-bound investment-research workflow for global AI-agent startups serving small and midsize businesses (SMBs), focused on seed through Series A. The output is a ranked shortlist of 10 companies, with the top 3 highlighted for follow-up.

The investment lens prioritizes fast growth and market size while accepting higher execution risk. The result is a research prioritization artifact, not a definitive investment recommendation.

## Scope

The research topic is **AI agents for SMB startups**. Candidates may operate across SMB-facing categories such as sales, customer support, finance, operations, or vertical software, provided that the agent capability is material to the product and the company fits the seed-to-Series-A scope when stage evidence is available.

The sourcing workflow will use the repository’s current flow path: Product Hunt and YC source snapshots as origin inputs, with Hacker News as optional enrichment. Candidates are deduplicated by canonical company domain, retaining name-based fallback only when usable domains are unavailable. Category coverage is a guardrail, not a quota: it should prevent concentration in one category when credible alternatives exist without forcing weak candidates into the shortlist.

## Research pipeline

The run follows the existing five-stage pipeline:

```text
topic and thesis
  -> source discovery and fit triage
  -> evidence normalization
  -> deterministic analysis
  -> company memos and run summary
```

The initialized run will request 10 retained candidates, enable full evidence coverage, and use the standard retry and atomic artifact-commit behavior. The source-of-truth remains the run directory and its manifest.

## Scoring rubric

Scores total 100 points:

| Category | Weight | Evaluation focus |
| --- | ---: | --- |
| Growth potential and momentum | 30 | Customer, revenue, usage, hiring, launch, distribution, or other credible momentum signals |
| Market size and expansion path | 30 | Size and urgency of the served SMB segment, adjacent workflows, and ability to expand beyond the initial wedge |
| Product differentiation and defensibility | 20 | Distinct workflow ownership, agent quality, integrations, data advantages, distribution, or other durable differentiation |
| SMB problem intensity and adoption fit | 15 | Frequency and cost of the problem, willingness to adopt, time-to-value, and fit with SMB buying behavior |
| Execution risk and capital efficiency | 5 | Evidence of efficient execution, while keeping this category intentionally low-weight under the selected thesis |

Scores must be traceable to normalized evidence. When a conclusion is inferred rather than directly reported, the analysis must label it as an inference and identify its supporting evidence. Missing evidence reduces confidence and is recorded as a gap; it is not silently converted into a factual negative.

## Evidence model

Each retained company will capture:

- canonical name, stable slug, website, category, stage, and one-line description;
- founder or team signals and funding signals when publicly available;
- growth indicators such as customers, revenue, usage, hiring, launches, or distribution;
- market evidence for the served SMB segment and expansion path;
- product capabilities, owned workflow, integrations, and differentiation;
- source URLs and dates for material claims; and
- company-level evidence gaps and confidence notes.

Source provenance must remain attached to the claims it supports. The workflow must preserve excluded candidates and their exclusion reasons rather than dropping them without explanation.

## Artifacts and final deliverable

The run will produce:

- `sourcing/candidates.json` with retained and excluded candidates plus provenance;
- one normalized evidence artifact per company;
- one deterministic analysis artifact per company;
- one concise memo per company; and
- `run-summary.md` containing the ranked list, top 3 priority companies, skipped candidates, unresolved gaps, retries, and failures.

The final summary must distinguish verified facts, inferred judgments, and unresolved gaps. The top 3 are companies to prioritize for diligence or a meeting; the summary must not overstate the evidence as an investment decision.

## Error handling and validation

The workflow will preserve failed retrieval envelopes and allow one targeted retry per company. Incomplete or failed stages must be visible in the manifest and final summary. A company may not receive a confident ranking when required evidence artifacts are absent or invalid.

Before completion:

1. Run preflight with the same Python interpreter used for the workflow.
2. Validate all current-layout artifacts and the manifest.
3. Confirm that all retained companies have stable IDs, canonical websites, category labels, and provenance.
4. Confirm that every score is evidence-linked or explicitly labeled as an inference.
5. Run the repository’s offline test suite covering artifact contracts, lifecycle, evidence coverage, scoring behavior, and CLI compatibility.

Ranking ties are broken first by evidence completeness and then by growth signals. Validation failures must be fixed or reported as failures; they may not be hidden by rewriting the summary.

## Out of scope

- Making an investment decision or providing financial advice.
- Building a production AI agent or startup operating system.
- Exhaustive coverage of every SMB-agent company worldwide.
- Treating unverified funding, revenue, or customer claims as facts.
- Adding new external integrations when the current source-snapshot flow can satisfy the research run.
