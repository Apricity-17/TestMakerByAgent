---
name: coverage-strategy
description: Coverage-driven iterative test supplementation strategy
triggers:
  - coverage
  - uncovered
  - missing
  - branch
  - line rate
  - supplement
  - iterate
---

# Coverage-Driven Iteration Strategy

## Coverage Quality Hierarchy
Not all uncovered lines are equal. Prioritize:

1. **Critical logic uncovered** — fix NOW (may indicate missing edge case test)
2. **Error handling uncovered** — fix (exception paths need testing)
3. **Conditional branches uncovered** — consider (if branch is semantically meaningful)
4. **Logging/print statements** — skip (not worth testing)
5. **Boilerplate/glue code** — skip (framework entry points, `if __name__ == "__main__"`)
6. **Dead code / defensive checks** — skip (may indicate unreachable code)

## Coverage Targets by Project Type
| Project Type | Reasonable Line Coverage | Notes |
|-------------|------------------------|--------|
| Library / SDK | 90-95% | Public API must be thoroughly tested |
| Web application | 75-85% | Templates, config, and routing add untestable code |
| CLI tool | 80-90% | Argument parsing is often boilerplate |
| Data science script | 60-70% | Exploratory code, visualization code is hard to test |
| One-off script | No target | Value is in execution, not testing |

## When to Stop Iterating
1. **Coverage target met** — stop
2. **Diminishing returns** — 2 consecutive rounds with < 2% improvement → stop
3. **Remaining code not worth testing** — logs, boilerplate, framework entry → stop
4. **Max iterations reached** — hard cap 5 rounds → stop

## Branch vs Line Coverage
- Branch coverage reveals untested condition outcomes (True/False for each `if`)
- Line coverage reveals which lines never execute
- A line can be "covered" but both branches not tested — track branch coverage
- For `if a and b` with 3 conditions, you need 4 paths, not 2

## Coverage Report Interpretation
- 100% line coverage ≠ good tests — assertions may be weak or missing
- Focus on MEANINGFUL assertions: test that correct values are returned, not just that code runs
- Check per-function coverage: a few functions at 60% drag down the total
