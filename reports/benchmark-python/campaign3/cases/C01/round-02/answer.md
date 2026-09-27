Here’s the project explanation, without changing any files.

### Entry point and function
- The entry point is `app.py`.
- It defines `main()`:
  - `main()` calls `print(clamp(8, 0, LIMIT))`.
- The script entry guard is:
  - `if __name__ == '__main__': main()`
- So running `app.py` directly executes `main()` and prints the result of `clamp(8, 0, LIMIT)`.

### The two imported modules
In `app.py`, the two imported modules/symbols are:
- `from calculator import clamp`
- `from settings import LIMIT`

Their roles:
- `calculator.py` provides `clamp(value, low, high)`, which returns:
  - `max(low, min(value, high - 1))`
- `settings.py` provides `LIMIT`, which is currently:
  - `LIMIT = 10`

### Config entry
- The config entry is `LIMIT` in `settings.py`.
- It is set to `10`.
- In `app.py`, that value is used as the upper bound passed into `clamp()`.

### Actual test command
- The test file is `test_calculator.py`.
- Its contents use `unittest` and define `ClampTests`.
- The file ends with:
  - `if __name__=='__main__': unittest.main()`
- The actual test command you asked for is:
  - `python -m unittest -v`

I did not run any commands; I only inspected the project files.
