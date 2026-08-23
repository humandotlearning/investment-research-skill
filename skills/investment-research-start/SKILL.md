---
name: investment-research-start
description: Use when starting or resuming a structured startup investment-research run from a topic, URL list, or feed.
compatibility: Requires Python 3.10+ and network access for Exa or agent-native web search
---

# Investment research entry point

Create and manage one evidence-bound research run. Keep the run directory as the source of truth.

## Workflow

1. Locate a working Python 3.10+ interpreter. Never install Python or repair aliases automatically.
2. Run `scripts/run.py preflight`. Exa is preferred when ready. If Exa is unavailable, use the current agent's native web-search capability and mark every fallback retrieval envelope with `provider: web`. If neither works, record a failed stage and surface the preflight remediation.
3. Prepare `input.json` and `thesis.md`, then run `scripts/run.py init`. Use the returned run only when it is new or resumable.
4. Activate `investment-research-sourcing`, then `investment-research-evidence`, `investment-research-analysis`, and `investment-research-memo` in that order.
5. Update each stage with `scripts/run.py stage`. Mark a stage completed only after its artifacts exist and validate.
6. Run `scripts/run.py validate`, fix current-layout errors, then write `run-summary.md` from validated results and validate once more.

Use the same interpreter for every command. Pass files and ordinary arguments; never construct shell-interpolated JSON or generated `python -c` commands.

## Input defaults

`input.json` accepts `seed`, `assumptions`, `sourcing`, `research`, and `recommendation_thresholds`. Defaults materialized by `init` are 15 sourced candidates, 8 deeply researched priority candidates, `research.full_coverage: false`, `Watch` at 65, and `Take a meeting` at 80.

## Run state

Statuses are `pending`, `running`, `completed`, `partial`, `failed`, and `skipped`. Resume only incomplete stages when the stored input/thesis fingerprint still matches. Preserve failed retrieval envelopes and retry artifacts as provenance.

Use `scripts/run.py commit --source TEMP --destination ARTIFACT --kind json|text` to validate and atomically promote agent-authored artifacts. Exit codes are 2 invalid input, 3 runtime or SDK, 4 authentication, 5 provider or network, 6 write, and 7 validation.

The final `run-summary.md` must use `## Decisions`, `## Skipped candidates`, `## Unresolved gaps`, `## Retries`, and `## Failures`. Report validated company scores and calls, every skipped comparable or exclusion, each company/category gap, whether the one retry was used, and every partial or failed stage. Use `None.` in an empty section. Do not summarize unvalidated scores.
