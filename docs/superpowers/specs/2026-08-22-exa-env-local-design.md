# Exa Local Credential Loading Design

## Scope

Allow the sourcing and research CLI helpers to obtain `EXA_API_KEY` from the
process environment or, when absent, from `.env.local` in the repository where
the command is run.

## Behavior

The process environment is authoritative. If it has no non-empty
`EXA_API_KEY`, the helper reads only `Path.cwd() / ".env.local"` and extracts a
single `EXA_API_KEY` assignment. It must never overwrite the environment,
search parent directories, print the key, or add a third-party dependency.

Both stage instructions will state this resolution order. Tests cover
environment precedence and the `.env.local` fallback without using a real key
or the network.
