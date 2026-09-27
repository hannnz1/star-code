Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound handling from `high - 1` to `high`.
- New logic: `return max(low, min(value, high))`

Result:
- Verification command `python -m unittest -v` passed.
- All 10 visible tests passed: `Ran 10 tests ... OK`

This keeps the function general for hidden tests by preserving inclusive upper-bound behavior.
