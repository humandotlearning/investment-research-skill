---
name: investment-research-memo
description: Use when turning a validated investment analysis into a concise decision memo without changing its score or recommendation.
compatibility: Requires Python 3.10+ and no additional network access after analysis
---

# Write the decision memo

Read the validated `analysis.md` and its referenced evidence. Keep the memo concise and decision-oriented. Separate known facts, company claims, inferences, and unresolved gaps in the prose.

The score and recommendation must copy analysis exactly. Use these required sections:

```markdown
# Company name

## Recommendation
**Pass**

## Score
**0 / 100**

## Why
Concise evidence-bound rationale.

## Risks and gaps
Material uncertainties and missing categories.

## Next step
One action consistent with the recommendation.
```

Do not introduce new claims or correct analysis inside the memo. If analysis is wrong, return to the analysis stage. Commit atomically; the validator must reject score or recommendation drift before promotion.
