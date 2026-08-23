---
name: investment-research-analysis
description: Use when scoring normalized startup evidence with a deterministic investment rubric and explicit evidence gaps.
compatibility: Requires Python 3.10+ and no additional network access after evidence collection
---

# Score the evidence

Read only the run input, thesis, selected candidate record, and company `evidence.json`. Do not add unsupported facts during analysis.

Score five categories from 0 to 20: Team, Product differentiation, Market attractiveness, Traction, and Thesis alignment. For each row, cite one or more comma-separated `claim:<id>` references or `gap:<category>` references. A row supported only by gaps receives zero points. Unavailable data never receives inferred score credit.

Use this exact parseable structure in `analysis.md`:

```markdown
| Category | Score | Evidence |
| --- | ---: | --- |
| Team | 0 | gap:team |
| Product differentiation | 0 | gap:product |
| Market attractiveness | 0 | gap:market |
| Traction | 0 | gap:traction |
| Thesis alignment | 0 | gap:product |
| **Final score** | **0 / 100** | |

## Recommendation
**Pass**
```

Sum the rows exactly. Derive the call from `input.json`: `Take a meeting` at or above `meeting_min`, `Watch` at or above `watch_min`, otherwise `Pass`. Commit atomically and mark analysis completed only after validation.
