Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound handling from `high - 1` to `high`
- Resulting function now clamps inclusively at the upper bound:
  - `return max(low, min(value, high))`

Verification:
- Ran `python -m unittest -v`
- Result: 10/10 visible tests passed, exit code 0


