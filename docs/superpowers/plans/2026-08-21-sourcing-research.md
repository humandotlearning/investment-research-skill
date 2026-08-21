# Sourcing and Research Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add simple Exa-backed sourcing and research scripts, stage contracts, and credential-free tests.

**Architecture:** Each script is a standalone Python CLI. It constructs an Exa
client from `EXA_API_KEY`, retrieves highlighted results, and emits JSON. The
stage skills convert that retrieval data to durable pipeline artifacts.

**Tech Stack:** Python 3.9+, standard-library `unittest`, `exa-py`.

## Global Constraints

- Only sourcing and research may use Exa.
- Preserve source URLs and never log API keys.
- Permit only one focused research retry.

### Task 1: Sourcing CLI [x]

**Files:** `skills/sourcing/scripts/search.py`, `tests/test_sourcing_search.py`

- [x] Add a failing mocked-SDK test for serializable sourcing results.
- [x] Implement `search_candidates(topic, thesis, target_count, api_key)`.
- [x] Verify the test passes.

### Task 2: Research CLI [x]

**Files:** `skills/research/scripts/research.py`, `tests/test_research_script.py`

- [x] Add a failing mocked-SDK test for a company-focused query.
- [x] Implement `research_company(name, website, focus, api_key)`.
- [x] Verify the test passes.

### Task 3: Skill contracts [x]

**Files:** `skills/sourcing/SKILL.md`, `skills/research/SKILL.md`

- [x] Document inputs, script use, artifact schemas, provenance, and the
  evidence gate.
- [x] Run `python -m unittest discover -s tests -v` and compile both scripts.
