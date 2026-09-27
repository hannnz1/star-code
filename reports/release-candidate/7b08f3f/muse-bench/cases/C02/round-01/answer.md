Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound logic from `high - 1` to `high`, making the upper bound inclusive:
  - `return max(low, min(value, high))`

Verification:
- Ran `python -m unittest -v`
- Result: 10/10 tests passed, exit code 0


