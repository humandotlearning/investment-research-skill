---
name: investment-research-sourcing
description: Use to discover and prepare a short, normalized list of startup candidates for an investment-research run using Exa. Do not use for deep diligence, scoring, analysis, or memo writing.
---

# Investment Research Sourcing

## Purpose

Answer one question: **which startups should enter the research pipeline?**

Use Exa for discovery only. Return 10–20 credible candidates with an initial
signal, but do not make an investment case or score a company here.

## Inputs

Require:

- `topic`, for example `AI agents for SMBs`;
- `thesis.md` or the locked thesis text; and
- `target_count` (default `15`, valid range `10`–`20`).

Use the run's sourcing directory as the output location.

## Exa retrieval

Prefer a non-empty `EXA_API_KEY` process environment value. If it is not set,
the helper reads `EXA_API_KEY` only from `.env.local` in the repository from
which the command is run. Never place a key in a command, source file, or
artifact.
Run the helper from the repository root:

```powershell
python skills/sourcing/scripts/search.py --topic "AI agents for SMBs" --thesis "Seed B2B companies with a recurring SMB workflow wedge" --target-count 15
```

The helper uses `exa-py` company search with highlights and writes raw,
URL-backed retrieval JSON to stdout. Capture only the data needed to build the
artifacts; do not save page HTML or unbounded raw responses.

If the helper reports a missing key, SDK, or Exa error, record a sourcing-stage
failure and stop. Do not switch to another search provider in this skill.

## Required output

Write `sourcing/candidates.json` as a JSON array. Each item must contain:

```json
{
  "name": "Acme",
  "website": "https://acme.example",
  "description": "Plain-language description of the company and product.",
  "team_signal": "Initial public signal, or Not found.",
  "traction_signal": "Initial public signal, or Not found.",
  "source_urls": ["https://acme.example"]
}
```

Also write `sourcing/sourcing.md`: a short, reviewer-readable account of the
query, thesis, number of results, excluded duplicates, and why each candidate
entered the pipeline.

## Candidate rules

1. Verify a candidate's website from an official page where possible.
2. Normalize the display name and canonicalize the website hostname.
3. Deduplicate first by canonical website, then by normalized company name.
4. Exclude entries without an identifiable company or a source URL.
5. Preserve source URLs for all descriptions and initial signals.
6. If fewer than the requested candidates are verifiable, return fewer and
   explain the shortfall. Do not pad the list with guesses.

Pass only `candidates.json`, the thesis, and explicit paths to the research
stage. Sourcing is one of the two skills permitted to use Exa.
