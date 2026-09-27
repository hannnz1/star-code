Done.

Diff in `calculator.py`:
- Changed `clamp` from:
  - `return max(low, min(value, high - 1))`
- To:
  - `return max(low, min(value, high))`

Result:
- Verified with `python -m unittest -v`
- All 10 visible tests passed
- Exit code: 0

This keeps `clamp` general for hidden tests and fixes the inclusive upper-bound bug.
