Here’s the project, without changing any files:

- **Entry point:** `app.py`
- **Entry-point function:** `main()`
- **What it does:** `main()` calls `clamp(8, 0, LIMIT)` and prints the result.
- **Import in `app.py`:**
  - `from calculator import clamp`
  - `from settings import LIMIT`

The **two imported modules** are:

1. **`calculator.py`**
   - Defines `clamp(value, low, high)`.
   - Implementation: `return max(low, min(value, high - 1))`

2. **`settings.py`**
   - Defines the config constant `LIMIT = 10`

So the app flow is:

- `app.py` imports `clamp` from `calculator.py`
- `app.py` imports `LIMIT` from `settings.py`
- `main()` prints `clamp(8, 0, LIMIT)`

The **test file** is:

- `test_calculator.py`
- It imports `unittest` and `clamp` from `calculator.py`
- It defines `ClampTests(unittest.TestCase)` and dynamically adds test methods for several input/output cases
- It ends with:
  - `if __name__=='__main__': unittest.main()`

### Actual test command
The project’s test command is:

```bash
python -m unittest -v
```

I did **not** run any commands beyond reading the files, so I’m not claiming test results.
