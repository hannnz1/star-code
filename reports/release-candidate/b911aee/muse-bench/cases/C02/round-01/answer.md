Fixed `clamp`’s inclusive upper-bound bug in `calculator.py` only.

Diff summary:
- Changed `clamp(value, low, high)` from:
  - `return max(low, min(value, high - 1))`
- To:
  - `return max(low, min(value, high))`

Result:
- Verified with `python -m unittest -v`
- Actual outcome: all 10 visible tests passed (`Ran 10 tests ... OK`)
