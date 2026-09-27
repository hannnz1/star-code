Fixed `clamp` in `calculator.py` only.

Diff:
- Changed the upper-bound logic from `high - 1` to `high`
- This makes the clamp inclusive of the upper bound and keeps the function general for hidden tests

Result:
- Verification passed with `python -m unittest -v`
- All 10 visible tests passed
- Exit code: 0
