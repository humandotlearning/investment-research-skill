# AI Agents for SMB Startups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the flow-v2 rubric contract for thesis-specific score labels, then run and validate a global seed-to-Series-A investment research workflow for 10 SMB AI-agent startups.

**Architecture:** Preserve the existing source-snapshot, evidence, analysis, memo, and manifest lifecycle. Generalize only rubric label parsing and evidence-area mapping so existing five-label runs remain valid while the new SMB thesis uses its approved category names and weights. Execute the run through the existing atomic artifacts and validation gates.

**Tech Stack:** Python 3.10+, Python standard library, `unittest`, Agent Skills markdown contracts, Product Hunt and YC source snapshots, optional Hacker News enrichment, and Codex web retrieval for current public evidence.

## Global Constraints

- Research global AI-agent startups serving small and midsize businesses, focused on seed through Series A.
- Produce a ranked shortlist of 10 companies, with the top 3 highlighted for follow-up.
- Prioritize fast growth and market size while accepting higher execution risk.
- Use weights: Growth potential and momentum 30; Market size and expansion path 30; Product differentiation and defensibility 20; SMB problem intensity and adoption fit 15; Execution risk and capital efficiency 5.
- Use Product Hunt and YC source snapshots as origin inputs, with Hacker News as optional enrichment.
- Preserve provenance for every material claim and preserve excluded candidates and failed retrievals.
- Allow one targeted retry per company only when coverage is missing.
- Do not build a production AI agent or make a definitive investment decision.
- Do not commit generated runs, source snapshots, caches, or local credentials.

---

## File map

- Modify `skills/investment-research-start/scripts/run.py`: accept rubric-defined category names, weights, and evidence-area mappings while retaining legacy defaults.
- Modify `skills/investment-research-analysis/SKILL.md`: document the dynamic rubric contract and SMB analysis table.
- Create `tests/fixtures/flow-v2/smb-ai-agents-rubric.json`: thesis-linked rubric fixture with the approved five categories and weights.
- Create `tests/test_custom_rubric.py`: regression coverage for custom labels, evidence mappings, weighted arithmetic, and legacy compatibility.
- Create generated inputs and artifacts under `runs/2026-08-24-ai-agents-smb/`; do not commit them.

### Task 1: Generalize rubric parsing without breaking legacy runs

**Files:**

- Modify: `skills/investment-research-start/scripts/run.py`
- Create: `tests/fixtures/flow-v2/smb-ai-agents-rubric.json`
- Create: `tests/test_custom_rubric.py`

**Interfaces:**

- Add `load_rubric_categories(run_dir: Path, errors: list[str]) -> list[dict]` returning normalized entries with `name`, `weight`, `evidence_areas`, and `company_claim_cap`.
- Keep `_rubric_weights(run_dir: Path, errors: list[str]) -> dict[str, int]` as a compatibility wrapper.
- Extend `_parse_analysis(..., rubric_categories: list[dict] | None = None)` so rows use stored rubric order and category weights.
- Preserve legacy mappings: Team→team, Product differentiation→product, Market→market, Traction→traction, Thesis alignment→product.

- [ ] **Step 1: Write failing tests.**

~~~python
class CustomRubricTests(unittest.TestCase):
    def test_custom_names_and_weights_are_accepted(self):
        run_dir = make_initialized_run_with_rubric(SMB_RUBRIC)
        result = run_module.validate_run(run_dir)
        self.assertTrue(result["valid"], result["errors"])

    def test_positive_score_requires_configured_evidence_area(self):
        run_dir = make_initialized_run_with_rubric(SMB_RUBRIC)
        write_analysis_row(run_dir, "Market size and expansion path", 1, "claim:product-1")
        result = run_module.validate_run(run_dir)
        self.assertFalse(result["valid"])
        self.assertTrue(any("market" in error.lower() for error in result["errors"]))

    def test_legacy_fixture_still_validates(self):
        run_dir = make_complete_legacy_run()
        result = run_module.validate_run(run_dir)
        self.assertTrue(result["valid"], result["errors"])

    def test_weighted_total_uses_configured_weights(self):
        run_dir = make_initialized_run_with_rubric(SMB_RUBRIC)
        write_analysis(run_dir, scores={
            "Growth potential and momentum": 30,
            "Market size and expansion path": 30,
            "Product differentiation and defensibility": 20,
            "SMB problem intensity and adoption fit": 15,
            "Execution risk and capital efficiency": 5,
        })
        result = run_module.validate_run(run_dir)
        self.assertTrue(result["valid"], result["errors"])
~~~

- [ ] **Step 2: Verify the tests fail against the current hard-coded parser.**

Run:

~~~powershell
python -m unittest tests.test_custom_rubric -v
~~~

Expected: FAIL because `_rubric_weights` rejects the new names and `_parse_analysis` uses fixed evidence mappings.

- [ ] **Step 3: Add the new rubric fixture.**

Use five categories with weights 30, 30, 20, 15, and 5. Each category has `evidence_areas`, optional `company_claim_cap`, and anchors with exactly keys `0`, `10`, and `20`:

~~~json
{
  "version": 2,
  "total_weight": 100,
  "categories": [
    {
      "name": "Growth potential and momentum",
      "weight": 30,
      "evidence_areas": ["traction", "freshness"],
      "company_claim_cap": 10,
      "anchors": {"0": "No credible growth or momentum evidence.", "10": "Partial momentum evidence exists.", "20": "Independent evidence supports strong momentum."}
    },
    {
      "name": "Market size and expansion path",
      "weight": 30,
      "evidence_areas": ["market"],
      "company_claim_cap": 10,
      "anchors": {"0": "No credible expandable SMB market evidence.", "10": "A plausible SMB market is identified.", "20": "Independent evidence supports a large expandable market."}
    },
    {
      "name": "Product differentiation and defensibility",
      "weight": 20,
      "evidence_areas": ["product", "competitors"],
      "company_claim_cap": null,
      "anchors": {"0": "No differentiated agent workflow evidence.", "10": "The product appears differentiated.", "20": "Independent evidence supports durable differentiation."}
    },
    {
      "name": "SMB problem intensity and adoption fit",
      "weight": 15,
      "evidence_areas": ["market", "product"],
      "company_claim_cap": 10,
      "anchors": {"0": "No evidence of urgent SMB pain or adoption fit.", "10": "A plausible pain and adoption path exist.", "20": "Independent evidence supports acute pain and adoption fit."}
    },
    {
      "name": "Execution risk and capital efficiency",
      "weight": 5,
      "evidence_areas": ["team", "traction"],
      "company_claim_cap": 5,
      "anchors": {"0": "No execution evidence.", "10": "Partial evidence suggests capable execution.", "20": "Independent evidence supports efficient execution."}
    }
  ]
}
~~~

- [ ] **Step 4: Implement rubric normalization and dynamic parsing.**

In `run.py`, validate nonempty unique names, positive integer weights, valid evidence areas from `team`, `product`, `market`, `traction`, `competitors`, and `freshness`, exactly five categories, total weight 100, and anchor keys `0/10/20`. Normalize absent `evidence_areas` and `company_claim_cap` from the legacy mapping. Update callers of `_parse_analysis` to pass the normalized category list. A positive score must cite a claim in one configured evidence area; gap-only rows must score zero; company-claim caps apply only when configured.

- [ ] **Step 5: Run focused and existing validation tests.**

~~~powershell
python -m unittest tests.test_custom_rubric tests.test_run_validation tests.test_flow_v2_lifecycle tests.test_flow_evidence_coverage -v
~~~

Expected: PASS for the new rubric and all existing legacy fixtures.

- [ ] **Step 6: Commit the compatibility change.**

~~~powershell
git add skills/investment-research-start/scripts/run.py tests/fixtures/flow-v2/smb-ai-agents-rubric.json tests/test_custom_rubric.py
git commit -m "feat: support thesis-specific investment rubrics"
~~~

### Task 2: Update the analysis skill contract

**Files:**

- Modify: `skills/investment-research-analysis/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1:** Replace the fixed-label instruction with the rubric-driven contract: read category names, weights, and `evidence_areas` from `rubric.json`; write rows in rubric order; permit scores up to each category weight; preserve the parseable final-score format.
- [ ] **Step 2:** Add the SMB category names and weights to the README, and state that generated run directories are not committed.
- [ ] **Step 3: Run the documentation-adjacent regression suite.**

~~~powershell
python -m unittest discover -s tests -v
~~~

Expected: PASS.

- [ ] **Step 4: Commit the contract documentation.**

~~~powershell
git add skills/investment-research-analysis/SKILL.md README.md
git commit -m "docs: describe thesis-specific SMB rubric"
~~~

### Task 3: Initialize the SMB AI-agent research run

**Files:**

- Create generated: `runs/2026-08-24-ai-agents-smb/input-source.json`
- Create generated: `runs/2026-08-24-ai-agents-smb/thesis-source.md`
- Create generated: `runs/2026-08-24-ai-agents-smb/manifest.json`

- [ ] **Step 1: Write the input.**

~~~json
{
  "seed": {"type": "topic", "value": "AI agents for SMB startups"},
  "assumptions": [],
  "sourcing": {"target_count": 10},
  "research": {"full_coverage": true},
  "recommendation_thresholds": {"watch_min": 65, "meeting_min": 80}
}
~~~

- [ ] **Step 2: Write the thesis.**

~~~markdown
# Investment thesis

Back AI-agent products serving SMBs that can scale rapidly across a large, urgent market. Prioritize credible growth and expansion potential over low execution risk, while requiring source-linked evidence for product differentiation, adoption fit, and momentum.
~~~

- [ ] **Step 3: Run preflight and initialize.**

~~~powershell
python skills/investment-research-start/scripts/run.py preflight --cwd .
python skills/investment-research-start/scripts/run.py init --run-dir runs/2026-08-24-ai-agents-smb --input runs/2026-08-24-ai-agents-smb/input-source.json --thesis runs/2026-08-24-ai-agents-smb/thesis-source.md --rubric tests/fixtures/flow-v2/smb-ai-agents-rubric.json
~~~

Expected: preflight reports a usable Python 3.10+ runtime and `recommended_provider: source_snapshots`; init reports `status: ok` and creates a resumable manifest.

- [ ] **Step 4: Confirm initialization has no input, thesis, rubric, or manifest errors.**

~~~powershell
python skills/investment-research-start/scripts/run.py validate --run-dir runs/2026-08-24-ai-agents-smb
~~~

Expected: only incomplete-stage errors remain.

### Task 4: Source and triage 10 candidates

**Files:**

- Create generated: `runs/2026-08-24-ai-agents-smb/source-snapshots/product-hunt.atom`
- Create generated: `runs/2026-08-24-ai-agents-smb/source-snapshots/yc-companies.json`
- Create generated: `runs/2026-08-24-ai-agents-smb/source-snapshots/hacker-news-items.json` when available
- Create generated: `runs/2026-08-24-ai-agents-smb/sourcing/retrieval.json`
- Create generated: `runs/2026-08-24-ai-agents-smb/sourcing/candidates.json`

- [ ] **Step 1:** Use Codex web retrieval to obtain current official Product Hunt and YC snapshots. Preserve raw inputs under `source-snapshots`. Obtain Hacker News only as enrichment; it cannot be a candidate origin.
- [ ] **Step 2: Normalize through the snapshot command.**

~~~powershell
python skills/investment-research-sourcing/scripts/search.py snapshots --input runs/2026-08-24-ai-agents-smb/input.json --thesis runs/2026-08-24-ai-agents-smb/thesis.md --product-hunt runs/2026-08-24-ai-agents-smb/source-snapshots/product-hunt.atom --yc runs/2026-08-24-ai-agents-smb/source-snapshots/yc-companies.json --hacker-news runs/2026-08-24-ai-agents-smb/source-snapshots/hacker-news-items.json --output runs/2026-08-24-ai-agents-smb/sourcing/candidates.json --retrieval-output runs/2026-08-24-ai-agents-smb/sourcing/retrieval.json
~~~

Omit `--hacker-news` if no snapshot is available.

- [ ] **Step 3:** Confirm `actual_count <= 10`, every retained company has a Product Hunt or YC origin, every retained company has a stable slug and canonical website, and exclusions retain reasons and provenance.
- [ ] **Step 4: Mark sourcing complete.**

~~~powershell
python skills/investment-research-start/scripts/run.py stage --run-dir runs/2026-08-24-ai-agents-smb --stage sourcing --status completed --provider source_snapshots --exit-code 0 --artifact sourcing/retrieval.json --artifact sourcing/candidates.json
~~~

### Task 5: Collect and normalize company evidence

**Files:**

- Create generated: `runs/2026-08-24-ai-agents-smb/companies/<slug>/retrieval-initial.json`
- Create generated: `runs/2026-08-24-ai-agents-smb/companies/<slug>/retrieval-retry.json` only when needed
- Create generated: `runs/2026-08-24-ai-agents-smb/companies/<slug>/evidence.json`

- [ ] **Step 1: Process each retained slug one at a time.**

~~~powershell
python skills/investment-research-evidence/scripts/research.py --candidates runs/2026-08-24-ai-agents-smb/sourcing/candidates.json --slug <slug> --output runs/2026-08-24-ai-agents-smb/companies/<slug>/retrieval-initial.json
~~~

Use official company sources first, then primary records and credible secondary sources. Collect team/execution, product, market, traction/freshness, and competitor evidence.

- [ ] **Step 2:** If initial coverage is incomplete, pass the complete normalized missing list to one `--focus` retry and write `retrieval-retry.json`. If coverage is complete, do not create a retry.
- [ ] **Step 3:** Write `evidence.json` with binary coverage for all six categories, normalized missing/unresolved lists, retrieval metadata, stable claim IDs, claim types, source quality, confidence, and source URLs present in retrieval provenance. Promote it atomically and mark the company research stage complete.

~~~powershell
python skills/investment-research-start/scripts/run.py commit --source runs/2026-08-24-ai-agents-smb/companies/<slug>/evidence.pending.json --destination runs/2026-08-24-ai-agents-smb/companies/<slug>/evidence.json --kind json
python skills/investment-research-start/scripts/run.py stage --run-dir runs/2026-08-24-ai-agents-smb --stage research --status completed --company <slug> --provider web --exit-code 0 --artifact companies/<slug>/evidence.json
~~~

Use `provider: exa` for Exa retrieval and `provider: web` for native web fallback. Preserve failed envelopes when neither works.

### Task 6: Score evidence and write company memos

**Files:**

- Create generated: `runs/2026-08-24-ai-agents-smb/companies/<slug>/analysis.md`
- Create generated: `runs/2026-08-24-ai-agents-smb/companies/<slug>/memo.md`

- [ ] **Step 1: Write one analysis per company in rubric order.**

~~~markdown
| Category | Score | Evidence |
| --- | ---: | --- |
| Growth potential and momentum | 0 | gap:traction |
| Market size and expansion path | 0 | gap:market |
| Product differentiation and defensibility | 0 | gap:product |
| SMB problem intensity and adoption fit | 0 | gap:market |
| Execution risk and capital efficiency | 0 | gap:team |
| **Final score** | **0 / 100** | |

## Recommendation
**Pass**
~~~

Replace zeroes only when evidence supports them. Maxima are 30, 30, 20, 15, and 5. Derive calls from thresholds: 80+ `Take a meeting`, 65–79 `Watch`, otherwise `Pass`.

- [ ] **Step 2:** Atomically promote each analysis and mark analysis complete.

~~~powershell
python skills/investment-research-start/scripts/run.py commit --source runs/2026-08-24-ai-agents-smb/companies/<slug>/analysis.pending.md --destination runs/2026-08-24-ai-agents-smb/companies/<slug>/analysis.md --kind text
python skills/investment-research-start/scripts/run.py stage --run-dir runs/2026-08-24-ai-agents-smb --stage analysis --status completed --company <slug> --exit-code 0 --artifact companies/<slug>/analysis.md
~~~

- [ ] **Step 3:** Write each memo with the required headings `# Company name`, `## Recommendation`, `## Score`, `## Why`, `## Risks and gaps`, and `## Next step`. Copy score and recommendation exactly from analysis.
- [ ] **Step 4:** Atomically promote each memo and mark memo complete.

~~~powershell
python skills/investment-research-start/scripts/run.py commit --source runs/2026-08-24-ai-agents-smb/companies/<slug>/memo.pending.md --destination runs/2026-08-24-ai-agents-smb/companies/<slug>/memo.md --kind text
python skills/investment-research-start/scripts/run.py stage --run-dir runs/2026-08-24-ai-agents-smb --stage memo --status completed --company <slug> --exit-code 0 --artifact companies/<slug>/memo.md
~~~

### Task 7: Assemble, validate, and hand off the ranked result

**Files:**

- Create generated: `runs/2026-08-24-ai-agents-smb/run-summary.md`

- [ ] **Step 1:** Build the summary from validated analyses using exactly these headings:

~~~markdown
## Decisions
## Skipped candidates
## Unresolved gaps
## Retries
## Failures
~~~

List all validated companies with score and recommendation under Decisions, identify the top 3, and record every excluded/skipped candidate, company/category gap, retry, and partial/failed stage. Use `None.` for empty sections.

- [ ] **Step 2: Run final validation.**

~~~powershell
python skills/investment-research-start/scripts/run.py validate --run-dir runs/2026-08-24-ai-agents-smb
~~~

Expected: `valid: true`, with no malformed artifacts, missing company artifacts, score arithmetic mismatch, memo drift, unsupported claim source, provenance mismatch, or summary-section error.

- [ ] **Step 3: Run the complete offline suite.**

~~~powershell
python -m unittest discover -s tests -v
~~~

Expected: all tests pass, including legacy flow and custom-rubric tests.

- [ ] **Step 4:** Mark validation complete, re-run validation, and hand off the generated `run-summary.md`. Report the top 3 and scores, unresolved gaps, and that the output is research prioritization rather than investment advice. Keep generated artifacts uncommitted.

## Self-review

- Spec coverage: scope and objective are covered by Tasks 3–7; rubric weights and provenance by Tasks 1, 5, and 6; failure handling by Tasks 5 and 7; validation and out-of-scope constraints by the global constraints and Task 7.
- Placeholder scan: no unfinished markers or incomplete requirement appears in the plan.
- Type consistency: rubric categories are normalized once, `_rubric_weights` remains a compatibility wrapper, and `_parse_analysis` receives the same category definitions used by validation.
- Scope: rubric compatibility is a prerequisite for the requested research run; no unrelated refactor or external integration is included.



