Here’s the project explanation, using the existing file and symbol names only.

## Entry point and function
- **File:** `app.py`
- **Entry point:** `if __name__ == '__main__': main()`
- **Main function:** `main()`
- **What it does:** `main()` calls `clamp(8, 0, LIMIT)` and prints the result.

## Two imported modules
In `app.py`:
1. `from calculator import clamp`
   - Imports the `clamp` function from `calculator.py`.
2. `from settings import LIMIT`
   - Imports the `LIMIT` constant from `settings.py`.

## Config entry
- **File:** `settings.py`
- **Config symbol:** `LIMIT = 10`
- This is the value used by `app.py` as the upper bound input to `clamp`.

## Actual test command
- The expected test command is: `python -m unittest -v`
- I did **not** run any commands, so I am not claiming this was executed.
- The repository’s test file is `test_calculator.py`, which defines `unittest` tests for `calculator.clamp`.

## Related symbols
- `calculator.py` defines `clamp(value, low, high)`, implemented as:
  - `return max(low, min(value, high - 1))`
- `test_calculator.py` defines `ClampTests(unittest.TestCase)` and dynamically adds test methods that check `clamp(...)` across multiple cases.

If you want, I can also summarize the behavior of `clamp` in one sentence.
