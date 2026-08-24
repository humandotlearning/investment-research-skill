# Task 2A1 Report: Flow-v2 lifecycle

## Status

Implemented the Task 2A1 lifecycle slice only: flow-v2 input normalization, strict thesis-bound rubric initialization, immutable flow fingerprints, and explicit superseding-run API/CLI linkage. No sourcing, company, memo, or run-summary validation from Task 2A2 was implemented.

## RED evidence

### Initial focused RED

Command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
```

Expected result before production code:

```text
FAILED (failures=1, errors=7)
```

The failures demonstrated the missing v2 behavior:

- `normalize_input` had no `version` and retained legacy defaults.
- `initialize_run` accepted no rubric argument and did not require `rubric.json`.
- missing-rubric initialization did not fail.
- no superseding-run API or CLI existed.
- the legacy fixture read-only validation test already passed.

### Self-review edge-case RED

After the initial implementation, self-review identified that an already populated destination run could be resumed and relinked by `supersede_run`.

Command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
```

Expected regression result:

```text
test_supersede_refuses_to_reuse_an_existing_destination_run ... FAIL
Ran 8 tests
FAILED (failures=1)
```

The production fix now rejects any non-empty superseding destination before creating or linking a run.

## GREEN evidence

### Focused lifecycle suite

Command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
```

Output summary:

```text
Ran 8 tests in 0.649s
OK
```

Coverage includes:

- v2 defaults and removal of the implicit research limit;
- strict non-empty thesis and exact five-category rubric contract;
- 20-point weights, 0/10/20 anchors, total weight 100, and thesis fingerprint binding;
- v2 input and manifest materialization;
- exact-flow resume behavior;
- changed input, topic, target, thesis, and rubric refusing in-place mutation;
- bidirectional superseding links through API and CLI;
- destination overwrite rejection;
- read-only legacy fixture validation.

### Full suite

Command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -v
```

Final output summary:

```text
Ran 73 tests in 5.238s
OK
```

The first full-suite run exposed two intentional compatibility assertions: the package helper allowlist still expected four scripts, and a legacy top-8 assertion expected `top priority` instead of v2 `full coverage`. Those assertions were updated to the approved v2 contract, after which all 73 tests passed.

## Files changed

- `skills/investment-research-start/scripts/flow_v2.py`
  - Standard-library-only v2 input, rubric, and fingerprint contracts.
- `skills/investment-research-start/scripts/run.py`
  - Delegates normalization/rubric work, requires rubric initialization, writes v2 manifests, exposes `supersede_run` and the `supersede` CLI.
- `tests/fixtures/flow-v2/input.json`
- `tests/fixtures/flow-v2/thesis.md`
- `tests/fixtures/flow-v2/rubric.json`
- `tests/test_flow_v2_lifecycle.py`
  - Focused RED/GREEN lifecycle contract.
- `tests/test_cli_contract.py`
- `tests/test_package_contract.py`
- `tests/test_run_script.py`
- `tests/test_run_validation.py`
  - Existing test setup and intentional v2 default/package assertions updated for required rubrics and the new helper module.

## Compatibility decisions

- Inputs without an explicit version normalize to v2; normalized input and new manifests contain `version: 2`.
- The v2 default has `research.full_coverage: true` and no `research.limit`. An explicitly supplied, valid `research.limit` remains representable for compatibility but is never synthesized as a default.
- `input_fingerprint` remains the canonical input-plus-thesis fingerprint used by the existing validator. New `rubric_fingerprint` and `flow_fingerprint` fields add rubric integrity and cover the complete input/thesis/rubric flow.
- The rubric requires a `thesis_fingerprint` equal to SHA-256 of the exact thesis text, making its non-empty 0/10/20 anchors machine-bound to that thesis.
- Legacy list-layout fixture validation remains read-only and unchanged.
- Supersession never rewrites old `input.json`, `thesis.md`, or `rubric.json`. The new manifest records `supersedes_run_id` and `supersedes_run_path`; after the new forward link is durable, the old manifest receives `superseded_by` lifecycle metadata.

## Self-review

- Confirmed `run.py` delegates the new contract to a focused sibling module rather than adding validator logic.
- Added and fixed the occupied-destination supersession regression.
- Confirmed same-directory and nested-directory supersession are rejected.
- Confirmed same-flow supersession is rejected and ordinary initialization never mutates a mismatched fingerprinted run.
- Confirmed no Task 2A2 sourcing/company/memo/summary validation was added.
- Full-suite failures were traced to contract assertions, not hidden production errors, and were minimally updated.

## Concerns

- Bidirectional links span two directories and cannot be transactionally atomic with standard filesystem primitives. The implementation writes the new run's forward link first and then attempts the old run's backward link, so a failure during the second atomic write can leave a valid forward-only link. Flow artifacts remain unchanged in that case.

## Review hardening follow-up

The review findings were addressed as a lifecycle-only follow-up. No Task 2A2 sourcing, company, memo, or summary validators were added.

### Follow-up RED evidence

Focused command:

```powershell
$failed=0
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
if ($LASTEXITCODE -ne 0) {$failed=1}
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_run_script.py' -v
if ($LASTEXITCODE -ne 0) {$failed=1}
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_run_validation.py' -v
if ($LASTEXITCODE -ne 0) {$failed=1}
exit $failed
```

Initial expected RED summaries:

```text
FlowV2LifecycleTests: Ran 12 tests; FAILED (failures=3, errors=1)
RunScriptTests: Ran 18 tests; FAILED (failures=1)
NewRunValidationTests: Ran 16 tests; FAILED (failures=1)
```

The failures proved that:

- resume did not reject rubric-fingerprint drift or a superseded run;
- anchor key validation depended on JSON key order;
- supersession wrote the new manifest twice and could not repair a failed backward link;
- malformed lifecycle links were not validated;
- `update_stage` mutated tampered/superseded v2 runs;
- list-shaped candidates could route a v2 manifest through legacy validation.

Self-review added a second semantic RED command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
```

Output summary:

```text
Ran 12 tests in 1.125s
FAILED (failures=1)
```

This regression proved that boilerplate overlap (`investment thesis`) could incorrectly satisfy thesis specificity when the only substantive thesis term was short (`AI`).

### Follow-up GREEN evidence

The focused command above completed with all three suites green:

```text
FlowV2LifecycleTests: Ran 12 tests in 0.999s — OK
RunScriptTests: Ran 18 tests in 0.490s — OK
NewRunValidationTests: Ran 16 tests in 1.652s — OK
Focused total: 46/46 passed
```

Full-suite command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -v
```

Final output summary:

```text
Ran 79 tests in 5.726s
OK
```

### Follow-up implementation and review notes

- `initialize_run` resume and every v2 `update_stage` now validate stored input, thesis, rubric, input fingerprint, rubric fingerprint, flow fingerprint, and lifecycle links before continuing. Active operations reject `superseded_by` runs.
- `validate_run` reads `manifest.json` first and always selects current/v2 validation for `manifest.version == 2`, regardless of candidate payload shape.
- A superseding run's initial manifest write contains its durable forward `supersedes_run_id` and `supersedes_run_path` link.
- A retry accepts only a destination whose flow fingerprint and forward link exactly match the requested supersession. It repairs a missing old-manifest backlink without rewriting any new-run artifact. Conflicting links remain errors.
- Rubric anchor keys are an order-independent exact set. Level texts must be distinct, and every anchor must share a normalized meaningful thesis token after excluding short tokens, common stopwords, and boilerplate `investment`/`thesis` labels.
- The previous cross-directory concern is now explicitly recoverable: a forward-only run left by a failed backward-link write is a supported retry state, while cross-directory atomicity remains unavailable.

## Final lifecycle-integrity follow-up

This follow-up closes the remaining Task 2A1 version-routing, referential-link, and pre-manifest recovery gaps. It does not add Task 2A2 sourcing, company, memo, or summary validators.

### RED evidence

Command:

```powershell
$failed=0
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_flow_v2_lifecycle.py' -v
if ($LASTEXITCODE -ne 0) { $failed=1 }
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_run_script.py' -v
if ($LASTEXITCODE -ne 0) { $failed=1 }
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -p 'test_run_validation.py' -v
if ($LASTEXITCODE -ne 0) { $failed=1 }
exit $failed
```

Captured RED output summaries:

```text
FlowV2LifecycleTests: Ran 14 tests in 1.542s; FAILED (failures=4, errors=1)
RunScriptTests: Ran 19 tests in 0.685s; FAILED (failures=2)
NewRunValidationTests: Ran 17 tests in 2.354s; FAILED (failures=3)
```

The failures demonstrated that no initialization marker survived a pre-manifest write failure, lifecycle links were only syntax-checked, missing/non-2 manifest versions allowed stage mutation, and list-shaped candidates downgraded malformed/current manifests to legacy validation.

### Focused GREEN evidence

The same three-suite command, rerun after implementation and full-diff self-review, produced:

```text
FlowV2LifecycleTests: Ran 14 tests in 1.837s — OK
RunScriptTests: Ran 19 tests in 0.674s — OK
NewRunValidationTests: Ran 17 tests in 2.223s — OK
Focused total: 50/50 passed
```

### Full-suite GREEN evidence

Command:

```powershell
& 'C:\ProgramData\anaconda3\python.exe' -m unittest discover -s tests -v
```

Output:

```text
Ran 83 tests in 7.112s
OK
```

### Files changed in this follow-up

- `skills/investment-research-start/scripts/flow_v2.py`
- `skills/investment-research-start/scripts/run.py`
- `tests/test_flow_v2_lifecycle.py`
- `tests/test_run_script.py`
- `tests/test_run_validation.py`
- `.superpowers/sdd/task-2a1-report.md`

### Compatibility and integrity decisions

- Any manifest is current-run intent even when malformed or version-drifted. A missing manifest still routes current when `rubric.json`, the initialization marker, or v2 `input.json` is present. Legacy validation requires the affirmative legacy candidates/sourcing/evidence layout and no v2 marker.
- `update_stage` requires a parsed object manifest with `version == 2`, then validates the stored flow, fingerprints, active status, and referential links before obtaining or mutating a stage record.
- Forward and backward links require absolute resolved target directories, locally valid target flow fingerprints, matching target run IDs, and reciprocal path/identity/fingerprint fields.
- Initialization writes an exact flow-and-forward-link marker before flow artifacts. A retry may rewrite only the same flow under a matching marker, rejects unrelated content, and removes the marker after the manifest is durable. Supersession still changes only the old manifest linkage; old input, thesis, and rubric bytes remain unchanged.
- Read-only validation of the affirmative legacy fixture remains supported. Candidate shape alone can no longer select legacy behavior.

### Final self-review and concerns

- Reviewed the complete lifecycle production diff from `5bb4a72`, not only this patch.
- Tightened marker recovery to reject nonempty nested `sourcing` or `companies` directories and to clean up an exact marker if a retry observes an already-durable destination manifest.
- Confirmed the required injected pre-manifest failure retries successfully and leaves all source-run flow artifacts byte-identical.
- Cross-directory bidirectional linkage cannot be one filesystem transaction; the explicit marker handles pre-manifest interruption, while the existing idempotent retry repairs interruption between the new forward manifest and old backward manifest.
- The deliberately simple anchor-overlap heuristic remains unchanged and may conservatively reject theses whose only meaningful terms are short/common tokens.
