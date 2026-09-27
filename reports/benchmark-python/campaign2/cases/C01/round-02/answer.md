Here’s a file-based explanation of the project, without changing anything.

## Entry point and function
- **Entry point file:** `app.py`
- **Entry-point function:** `main()`
- In `app.py`, `main()` calls `print(clamp(8, 0, LIMIT))`.
- The module also has the script guard:
  - `if __name__ == '__main__': main()`
- So running `app.py` directly executes `main()`.

## The two imported modules
In `app.py`, the imports are:

1. **`calculator`**
   - Imported symbol: `clamp`
   - Source file: `calculator.py`
   - Function definition in `calculator.py`:
     - `def clamp(value, low, high):`
   - Behavior:
     - `return max(low, min(value, high - 1))`

2. **`settings`**
   - Imported symbol: `LIMIT`
   - Source file: `settings.py`
   - Config value:
     - `LIMIT = 10`

## Config entry
- The config entry is `LIMIT` in `settings.py`.
- It is used by `app.py` as the upper bound argument in `clamp(8, 0, LIMIT)`.

## Actual test command
- The test file is `test_calculator.py`.
- It uses Python’s `unittest` framework and ends with:
  - `if __name__=='__main__': unittest.main()`
- Based on the project request, the actual test command is:
  - `python -m unittest -v`

## Notes
- I did **not** run any commands.
- I’m citing the existing file and symbol names exactly as they appear: `app.py`, `main()`, `clamp`, `LIMIT`, `calculator.py`, `settings.py`, and `test_calculator.py`.
