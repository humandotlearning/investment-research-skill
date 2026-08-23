---
name: investment-research-evidence
description: Use when collecting and normalizing provenance-preserving evidence for selected investment candidates.
compatibility: Requires Python 3.10+ and network access for Exa or agent-native web search
---

# Build company evidence

Research only candidates selected in `sourcing/candidates.json`. Work one company at a time so failures remain resumable.

## Retrieval passes

Run `scripts/research.py --candidates CANDIDATES --slug SLUG --output RETRIEVAL_INITIAL`. It stores no more than five deduplicated results with one highlight of at most 400 characters each.

After evaluating the initial pass, allow exactly one retry only when coverage is missing. Pass the complete normalized missing list with `--focus`; valid categories and order are `team`, `product`, `market`, `traction`, `competitors`, and `freshness`. Write the retry to `retrieval-retry.json`. Never retry an empty list or perform a second retry.

If Exa fails, preserve the failed envelope and use native web search when available. Store fallback output in the same schema with `provider: web`. If neither provider works, mark research failed or partial with remediation.

## Evidence contract

Create one `evidence.json` per company. It contains:

- `coverage`, with every category set only to `present` or `missing`;
- `missing_categories`, in the normalized category order;
- `unresolved_gaps`, exactly matching the final normalized missing-category list;
- `initial_missing_categories` when a retry occurs, containing the complete normalized list passed to that retry;
- `initial_coverage` when a retry occurs, preserving the binary coverage snapshot from which that list was derived;
- `retrievals`, each recording artifact path, provider, query, retrieved time, status, exit code, and bounded error metadata;
- `claims`, each with a stable ID, area, concise claim, claim type, source URL, source quality, and confidence.

Claim types are `verified_fact`, `company_claim`, `secondary_report`, `inference`, and `unknown`. Source quality is `first_party`, `primary_record`, `credible_secondary`, or `unknown`. Confidence is `high`, `medium`, or `low`.

Do not silently upgrade company claims or inferences to facts. A non-unknown claim needs a source URL present in the retrieval provenance. Commit the evidence atomically before marking research completed.
