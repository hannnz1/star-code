Updated `calculator.py` only.

Diff:
- Changed `clamp(value, low, high)` from:
  - `return max(low, min(value, high - 1))`
- to:
  - `return max(low, min(value, high))`

Result:
- Verified with `python -m unittest -v`
- All 10 visible tests passed
- Exit code: 0


