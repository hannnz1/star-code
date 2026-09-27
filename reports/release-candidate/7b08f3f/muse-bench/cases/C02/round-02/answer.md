Fixed `clamp` in `calculator.py` only.

Diff summary:
- Changed the upper-bound handling from `high - 1` to `high`
- Final behavior: `return max(low, min(value, high))`

Result:
- Verification command `python -m unittest -v` passed
- All 10 visible tests passed
- Exit code: 0

This keeps the function general for hidden tests and corrects the inclusive upper bound bug.
