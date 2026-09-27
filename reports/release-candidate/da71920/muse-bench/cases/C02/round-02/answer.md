Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound clamp from `high - 1` to `high`:
  - `return max(low, min(value, high))`

Result:
- Verified with `python -m unittest -v`
- All 10 visible tests passed
- Exit code: 0

This preserves general behavior for hidden tests by making the upper bound inclusive.
