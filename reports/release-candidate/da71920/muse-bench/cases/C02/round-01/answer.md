Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound handling from `high - 1` to `high`
- New logic: `return max(low, min(value, high))`

Result:
- Verified with `python -m unittest -v`
- All 10 visible tests passed
- Actual result: `Ran 10 tests ... OK`
