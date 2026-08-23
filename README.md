# Investment Research Skills

A small, portable skill package for evidence-bound startup investment research. It follows the [Agent Skills specification](https://agentskills.io/specification) and the focused entry-point pattern from [evals-skills](https://github.com/ai-evals-course/evals-skills). One entry-point skill coordinates four focused stages; three self-contained Python helpers provide run state, Exa retrieval, atomic writes, and validation.

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

## Requirements and provider setup

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

The helpers never print or persist the key. They do not install dependencies. Exa is preferred; after a preflight or retrieval failure, the active agent may use native web fallback and must tag the retrieval envelope with `provider: web`.

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

## Start a run

Create a small source input and a thesis:

```json
{
  "seed": {"type": "topic", "value": "AI agents for small businesses"},
  "assumptions": []
}
```

```sh
python skills/investment-research-start/scripts/run.py preflight
python skills/investment-research-start/scripts/run.py init --run-dir runs/2026-08-23-ai-agents-smb --input request.json --thesis thesis.md
```

The initializer materializes defaults of 15 sourced candidates, 8 priority candidates for deep research, `research.full_coverage: false`, `Watch` from 65, and `Take a meeting` from 80.

Then invoke the `investment-research-start` skill. It coordinates sourcing, evidence, analysis, memo, manifest updates, atomic commits, and final validation.

## Resume and validate

Run the same `init` command to resume. Resume succeeds only when normalized input and thesis hashes match the manifest; completed work is not repeated.

```sh
python skills/investment-research-start/scripts/run.py validate --run-dir runs/2026-08-23-ai-agents-smb
```

The validator auto-detects the prior layout for read-only regression checks. It never rewrites legacy artifacts.

## Run layout

```text
runs/<run-id>/
├── input.json
├── thesis.md
├── manifest.json
├── sourcing/
│   ├── retrieval.json
│   └── candidates.json
├── companies/<slug>/
│   ├── retrieval-initial.json
│   ├── retrieval-retry.json
│   ├── evidence.json
│   ├── analysis.md
│   └── memo.md
└── run-summary.md
```

`retrieval-retry.json` exists only when one targeted retry was necessary.

## Tests

Tests are offline and mock provider responses:

```sh
python -m unittest discover -s tests -v
```

Use an optional manual smoke run for live Exa or native-search fallback. Never commit `.env.local`, generated runs, caches, virtual environments, or local package directories.
