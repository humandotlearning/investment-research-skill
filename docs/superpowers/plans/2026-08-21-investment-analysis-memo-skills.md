# Investment Analysis and Memo Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-bound analysis and memo skills that work with the current and preferred investment-research artifact layouts.

**Architecture:** The analysis skill is the sole decision and scoring stage and accepts explicit paths to a locked thesis and evidence. The memo skill is a presentation stage that accepts analysis plus supporting evidence, preserving the analysis decision and provenance. Both support explicit paths in the current split layout and the future per-startup layout.

**Tech Stack:** Markdown Agent Skills specification; bundled Python `quick_validate.py` validator.

## Global Constraints

- Neither new skill may browse, call Exa, or rely on information outside supplied artifacts.
- Analysis scores exactly five 20-point categories and totals them arithmetically.
- Memo uses exactly one of `Pass`, `Watch`, or `Take a meeting`.
- Artifact compatibility is path-based; neither skill moves or renames files.
- Do not modify existing stage skills in this change.

---

### Task 1: Create the analysis skill

**Files:**

- Create: `skills/analysis/SKILL.md`
- Test: bundled validator applied to `skills/analysis`

**Interfaces:**

- Consumes: explicit paths to `thesis.md`, candidate data, `evidence.md`, and `sources.json`.
- Produces: an explicit `analysis.md` path in either supported artifact layout.

- [ ] **Step 1: Verify the failing baseline**

Run: `if (Test-Path skills/analysis/SKILL.md) { exit 1 } else { Write-Error 'analysis skill is missing'; exit 1 }`

Expected: non-zero exit with `analysis skill is missing`.

- [ ] **Step 2: Write the minimal analysis skill**

Create a Markdown Agent Skill that specifies evidence-only reasoning, the explicit compatibility contract, required analysis sections, the five 20-point scoring criteria, arithmetic scoring, unknown-evidence treatment, and output rules.

- [ ] **Step 3: Validate the new skill**

Run: `python C:\Users\nithi\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/analysis`

Expected: `Skill is valid!`

- [ ] **Step 4: Inspect the behavior contract**

Confirm the skill states that it cannot browse or use Exa, no uncited facts can enter analysis, and a missing signal is expressed as an evidence gap rather than a negative fact.

### Task 2: Create the memo skill

**Files:**

- Create: `skills/memo/SKILL.md`
- Test: bundled validator applied to `skills/memo`

**Interfaces:**

- Consumes: explicit paths to candidate data, `evidence.md`, `sources.json`, and `analysis.md`.
- Produces: an explicit `memo.md` path in either supported artifact layout.

- [ ] **Step 1: Verify the failing baseline**

Run: `if (Test-Path skills/memo/SKILL.md) { exit 1 } else { Write-Error 'memo skill is missing'; exit 1 }`

Expected: non-zero exit with `memo skill is missing`.

- [ ] **Step 2: Write the minimal memo skill**

Create a Markdown Agent Skill that specifies its non-research, non-reconsideration boundary, explicit compatibility contract, one-page structure, one recommendation vocabulary, evidence-gap disclosure, score preservation, and selected source attribution.

- [ ] **Step 3: Validate the new skill**

Run: `python C:\Users\nithi\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/memo`

Expected: `Skill is valid!`

- [ ] **Step 4: Inspect the behavior contract**

Confirm the skill forbids browsing and score changes, requires one recommendation, and makes material uncertainty visible rather than silently omitting it.

### Task 3: Verify the integrated deliverable

**Files:**

- Verify: `skills/analysis/SKILL.md`
- Verify: `skills/memo/SKILL.md`

**Interfaces:**

- Confirms that both skills consume only downstream artifacts and preserve the current and preferred layouts.

- [ ] **Step 1: Run both validators**

Run: `python C:\Users\nithi\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/analysis; python C:\Users\nithi\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/memo`

Expected: `Skill is valid!` twice.

- [ ] **Step 2: Review contract coverage**

Confirm analysis includes all rubric dimensions and explicit open questions; confirm memo includes every partner-facing section and selected source links. Confirm neither skill contains an Exa invocation or web-search instruction.
