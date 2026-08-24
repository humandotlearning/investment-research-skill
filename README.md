# Investment Research Skills

A small, portable skill package for evidence-bound startup investment research. It follows the [Agent Skills specification](https://agentskills.io/specification) and has a focused entry-point pattern. One entry-point skill coordinates four focused stages; three self-contained Python helpers provide run state, Exa retrieval, atomic writes, and validation.

[Walkthrough Video](https://drive.google.com/file/d/1X6fQWyiqrMcG8SJrori5fE86TBcr3EA-/view?usp=sharing)

## Architecture

```text
skills/
├── investment-research-start/       # entry point, run lifecycle, validation
├── investment-research-sourcing/    # discovery and fit triage
├── investment-research-evidence/    # research and evidence normalization
├── investment-research-analysis/    # deterministic 100-point score
└── investment-research-memo/        # concise decision memo
```

New runs keep machine-readable sourcing in `candidates.json` and company evidence in one `evidence.json`. The manifest records stage status, attempts, providers, errors, artifacts, and timestamps. Artifacts are promoted atomically, so an interrupted write cannot masquerade as completed work.

## Install for an agent

Install all five skills with the open Agent Skills CLI:

```sh
npx skills add https://github.com/humandotlearning/investment-research-skill
```

Or copy/link the five directories under `skills/` into a supported skills location. Keep all five together so the entry point can activate each stage by name.

- **Claude Code:** use the included `.claude-plugin/plugin.json` as an optional adapter, or install the skill directories in a Claude skills location.
- **Codex:** place the skill directories in a repository `.agents/skills/` directory or the configured personal skills directory.
- **Hermes:** use project `.hermes/skills/` or user `~/.hermes/skills/`.
- **OpenClaw:** use project `skills/` or user `~/.openclaw/skills/`.

These are ordinary Agent Skills: core instructions do not depend on vendor-specific tool names. Client discovery and trust settings still belong to the client.

## Requirements and provider setup

> Note: Requirements are not mandatory as the skill is written in a way to handle it if the below requirements are not satisfied, although having them improves the speed, iteration and quality of the research

- Python 3.10 or newer for managed runs and validation.
- Optional `exa-py` plus `EXA_API_KEY` for automated retrieval.
- An agent with native search capability for web fallback when Exa is unavailable.

Install Exa in your own environment if wanted:

```sh
python -m pip install exa-py
```

Set `EXA_API_KEY` in the environment, or put it in a repository-local `.env.local`:

```text
EXA_API_KEY=your-key
```

The helpers never print or persist the key. They do not install dependencies. Current flows use Product Hunt and YC source snapshots with provider `source_snapshots`, and Hacker News only as an enrichment signal. Exa and native web fallback remain legacy-compatible retrieval providers for older layouts.


## Run layout

```text
runs/<run-id>/
├── input.json                         # normalized run configuration and research seed
├── thesis.md                          # investment thesis used to evaluate companies
├── manifest.json                      # run lifecycle state, fingerprints, and artifact records
├── sourcing/
│   ├── retrieval.json                 # raw sourcing retrieval envelope and provider metadata
│   └── candidates.json                # normalized candidate companies selected for research
├── companies/<slug>/
│   ├── retrieval-initial.json         # initial company-specific retrieval envelope
│   ├── retrieval-retry.json           # targeted retry retrieval envelope, when needed
│   ├── evidence.json                  # normalized evidence supporting the company research
│   ├── analysis.md                    # scored analysis against the investment rubric
│   └── memo.md                        # concise company decision memo
└── run-summary.md                     # validated run-level decisions, gaps, retries, and failures
```

`retrieval-retry.json` exists only when one targeted retry was necessary.

## Tests

Tests are offline and mock provider responses:

```sh
python -m unittest discover -s tests -v
```

Use an optional manual smoke run for live Exa or native-search fallback. Never commit `.env.local`, generated runs, caches, virtual environments, or local package directories.
