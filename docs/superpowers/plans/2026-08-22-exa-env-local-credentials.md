# Exa Local Credential Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Exa CLI helpers resolve `EXA_API_KEY` from the environment or the host repository's `.env.local`.

**Architecture:** Add a small, standard-library credential resolver used by both helper entry points. The resolver checks the current process environment first, then reads only the current working directory's `.env.local`. Stage documentation mirrors that exact contract.

**Tech Stack:** Python 3.9+, standard-library `unittest`, Markdown.

## Global Constraints

- Environment values take precedence over `.env.local` values.
- Read only the current working directory's `.env.local`; do not search parents.
- Never emit, persist, or include credentials in artifacts.
- Do not add dependencies.

---

### Task 1: Credential resolution

**Files:**
- Modify: `skills/sourcing/scripts/search.py`
- Modify: `skills/research/scripts/research.py`
- Test: `tests/test_sourcing_search.py`
- Test: `tests/test_research_script.py`

**Interfaces:**
- Produces: `_load_api_key()` in each helper, returning a non-empty `str` or `None`.
- Consumes: `os.environ`, `Path.cwd() / ".env.local"`.

- [ ] **Step 1: Write failing tests**

```python
with patch.dict(os.environ, {"EXA_API_KEY": "environment-key"}, clear=True):
    self.assertEqual(module._load_api_key(), "environment-key")

with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temp_dir:
    Path(temp_dir, ".env.local").write_text("EXA_API_KEY=local-key\n", encoding="utf-8")
    with patch.object(module.Path, "cwd", return_value=Path(temp_dir)):
        self.assertEqual(module._load_api_key(), "local-key")
```

- [ ] **Step 2: Run the targeted tests and confirm they fail because `_load_api_key` is absent.**

Run: `python -m unittest tests.test_sourcing_search tests.test_research_script -v`

- [ ] **Step 3: Add the minimal resolver and use it in each CLI `main()`.**

```python
def _load_api_key():
    api_key = os.environ.get("EXA_API_KEY")
    if api_key:
        return api_key
    env_file = Path.cwd() / ".env.local"
    # Return the single EXA_API_KEY assignment if present.
```

- [ ] **Step 4: Run the targeted tests and confirm they pass.**

Run: `python -m unittest tests.test_sourcing_search tests.test_research_script -v`

### Task 2: Stage setup instructions

**Files:**
- Modify: `skills/sourcing/SKILL.md`
- Modify: `skills/research/SKILL.md`

**Interfaces:**
- Consumes: the helper resolution contract from Task 1.
- Produces: identical, safe operator instructions for both Exa stages.

- [ ] **Step 1: State that a non-empty environment value is preferred and `.env.local` in the command's working repository is the fallback.**

- [ ] **Step 2: Retain the prohibition on placing a key in commands, sources, or artifacts.**

- [ ] **Step 3: Run the complete test suite and compile both helpers.**

Run: `python -m unittest discover -s tests -v; python -m py_compile skills/sourcing/scripts/search.py skills/research/scripts/research.py`
