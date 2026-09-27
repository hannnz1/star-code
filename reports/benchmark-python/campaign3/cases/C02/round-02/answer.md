Done.

Diff in `calculator.py`:
- Changed `clamp` from exclusive upper bound logic:
  - `min(value, high - 1)`
- to inclusive upper bound logic:
  - `min(value, high)`

Actual result:
- Verified with `python -m unittest -v`
- 10/10 visible tests passed
- Exit code: 0
