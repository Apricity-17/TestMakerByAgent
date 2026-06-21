---
name: boundary-analysis
description: Systematic boundary condition analysis for test generation
triggers:
  - boundary
  - edge case
  - null
  - empty
  - zero
  - extreme
  - max
  - min
  - range
---

# Boundary Condition Analysis

## Numeric Boundaries
- Zero: `0` (always test!)
- Negative: `-1`, `-sys.maxsize`
- Positive maximum: `sys.maxsize`, `float('inf')`
- Floating point: `0.0`, `-0.0`, `float('nan')`, `float('inf')`
- Off-by-one: `n-1`, `n`, `n+1` at any condition threshold
- Type boundaries: `int` vs `float` when function expects specific type

## Collection Boundaries
- Empty: `[]`, `{}`, `set()`, `""`, `()` — the most important boundary
- Single element: `[x]` — often reveals off-by-one bugs
- Large: `list(range(1000))` — performance and recursion limits
- Duplicates: `[1, 1, 1]` — uniqueness assumptions

## String Boundaries
- Empty: `""` — separate from whitespace-only
- Whitespace: `"   "`, `"\t"`, `"\n"`
- Special characters: `"<script>"`, `"; DROP TABLE"`, null byte `"\0"`
- Unicode: `"中文"`, `"emoji 🎉"`, combining characters
- Very long: 10000+ characters

## Time Boundaries
- Past: Unix epoch 0, negative timestamps
- Future: Year 2038, far future
- Timezone: UTC vs local vs DST transitions

## Reference Boundaries
- `None` — always test if parameter accepts Optional
- Self-reference: object that points to itself
- Circular structures: `a.b = b; b.a = a`

## State Boundaries
- Uninitialized: before any setup
- Partially initialized: some fields set, others not
- Destroyed/closed: after `.close()` or cleanup
- Concurrent: two operations interleaved

## Test Order
1. Test `None`/empty FIRST — simplest, most impactful
2. Test zero/negative for numeric params
3. Test exact threshold values from condition checks
4. Test extreme values last — often not practical
