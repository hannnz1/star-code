Here’s what this project does, using the existing file and symbol names only:

- **Entry point:** `app.py`
  - It imports `clamp` from `calculator` and `LIMIT` from `settings`.
  - It defines `main()`, which does `print(clamp(8, 0, LIMIT))`.
  - The script entry guard is `if __name__ == '__main__': main()`, so running `app.py` executes `main()`.

- **Function:** `clamp` in `calculator.py`
  - Definition: `def clamp(value, low, high):`
  - Behavior: `return max(low, min(value, high - 1))`
  - In plain terms, it constrains `value` to be at least `low` and at most `high - 1`.

- **Imported modules used by `app.py`:**
  - `calculator` — specifically the symbol `clamp`
  - `settings` — specifically the symbol `LIMIT`

- **Config entry:** `LIMIT` in `settings.py`
  - Defined as `LIMIT = 10`
  - In `app.py`, this becomes the upper bound passed to `clamp(8, 0, LIMIT)`.

- **Test file and actual test command:**
  - The test file is `test_calculator.py`
  - It imports `unittest` and `clamp`
  - It defines `ClampTests(unittest.TestCase)` and dynamically adds test methods that exercise `clamp` across several inputs
  - The actual command to run the tests is:
    - `python -m unittest -v`

I did **not** run any commands, so I’m not claiming any test results.
