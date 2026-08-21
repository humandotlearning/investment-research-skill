# Sourcing and Research Skills Design

## Scope

Add focused sourcing and research skills with Python Exa helpers. Do not modify
the existing start, analysis, or memo skills.

## Sourcing

`skills/sourcing/SKILL.md` accepts a topic, thesis, target count, and output
path. Its script uses `EXA_API_KEY` and the official `exa-py` SDK to issue an
Exa company search with highlights. The skill normalizes and de-duplicates the
results into `candidates.json`.

## Research

`skills/research/SKILL.md` accepts one candidate and an output directory. Its
script retrieves URL-backed results for company, team, product, market,
traction, funding, competitors, technical signals, and risks. The skill writes
`evidence.md` and `sources.json`, assesses coverage, and allows one targeted
retry for missing public evidence.

## Constraints

- Only sourcing and research use Exa.
- API keys are read only from `EXA_API_KEY` and never printed.
- Scripts output JSON to stdout and fail clearly for missing credentials or SDK.
- Tests mock the SDK and require neither credentials nor network access.
