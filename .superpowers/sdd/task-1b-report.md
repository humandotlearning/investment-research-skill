# Task 1B Report — Source Adapter Contracts (GREEN)

## Scope and implementation plan

Task 1B creates the focused, standard-library-only assignment-v2 adapter module at `skills/investment-research-sourcing/scripts/sources.py`. Its boundaries are:

- Parse Product Hunt Atom snapshots and normalize YC directory/profile snapshots into intermediate source records.
- Validate that origins are complete and only Product Hunt or YC records from their exact official hosts.
- Normalize and deduplicate valid records by canonical website domain; use normalized company names only if one side has no usable domain; preserve every allowed origin.
- Enrich already-normalized candidates with matching Show HN freshness and traction signals, never an HN origin.

The legacy Exa retrieval helper remains unchanged and is not imported by, or otherwise coupled to, the new module.

## Inherited RED evidence

The Task 1A report recorded the intentional pre-implementation failure: `sources.py` was absent, so the source-adapter contract could not load it.

Task 1B independently reproduced that RED state before writing production code:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest tests.test_source_adapters -v
```

Output summary: exit code `1`; `ERROR: setUpClass (tests.test_source_adapters.SourceAdapterTests)`; `FileNotFoundError` for `skills\investment-research-sourcing\scripts\sources.py`; `Ran 0 tests in 0.001s`; `FAILED (errors=1)`.

## Focused GREEN

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest tests.test_source_adapters -v
```

Output summary: exit code `0`; all 10 source-adapter contract tests passed; `Ran 10 tests in 0.035s`; `OK`.

The focused suite was first made green, then re-run after self-review boundary hardening. It verifies Product Hunt Atom parsing, YC normalization, exact origin-domain enforcement, provenance-preserving exclusions, domain/name deduplication, HN domain precedence and name fallback, required signals, and stable ranking.

## Complete-suite verification

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -v
```

Output summary: exit code `0`; all 55 tests passed; `Ran 55 tests in 2.878s`; `OK`.

## Files changed

- `skills/investment-research-sourcing/scripts/sources.py` — new offline, standard-library adapter and normalization module.
- `tests/test_package_contract.py` — updates the exact helper inventory from three to four and still compiles every helper.
- `.superpowers/sdd/task-1b-report.md` — this report.

## Self-review

- Confirmed Product Hunt and YC are the only accepted origin types and source hosts are exact-match validated over HTTPS.
- Confirmed company URLs are normalized independently of origin URLs and Exa is not imported or called.
- Confirmed merge behavior is deterministic, retains Product Hunt/YC provenance, chooses a canonical root website where available, and never uses HN as an origin.
- Confirmed candidate eligibility requires source-linked freshness or traction evidence, while partial website records can join a matching valid record before final candidate validation.
- Ran `git diff --check`; it reported no whitespace errors.

## Concerns

None. The runtime stays standard-library-only and operates solely on supplied snapshots, so it remains offline-testable.
