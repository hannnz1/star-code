Here’s the project, without changing any files:

- **Entry point:** `app.py`
  - It imports `clamp` from `calculator` and `LIMIT` from `settings`.
  - The entry function is **`main()`**.
  - `main()` calls `print(clamp(8, 0, LIMIT))`.
  - The script runs that function under the guard **`if __name__ == '__main__': main()`**.

- **Two imported modules used by the entry point:**
  1. **`calculator.py`**
     - Defines **`clamp(value, low, high)`**
     - Implementation: `return max(low, min(value, high - 1))`
  2. **`settings.py`**
     - Defines the config entry **`LIMIT = 10`**

- **Test file:** `test_calculator.py`
  - Imports `unittest` and **`clamp`** from `calculator`.
  - Defines **`ClampTests(unittest.TestCase)`**.
  - Dynamically adds test methods that call `clamp(...)` with several inputs and expected outputs.
  - The file’s own runnable test entry point is **`if __name__=='__main__': unittest.main()`**.

- **Actual test command:** `python -m unittest -v`
  - I did **not** run this command, so I’m not claiming any test result.
  - It is the standard unittest discovery/run command for this project.

If you want, I can also summarize the exact behavior of `clamp()` in one sentence.
