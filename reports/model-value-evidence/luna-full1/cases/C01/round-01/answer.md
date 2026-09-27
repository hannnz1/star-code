`app.py` is the entry point: when run directly, its `if __name__ == '__main__'` block calls `main()`. `main()` calls `clamp(8, 0, LIMIT)` and prints the result.

It imports two modules: `calculator`, which provides `clamp(value, low, high)`, and `settings`, which provides the config entry `LIMIT = 10`. In `calculator.py`, `clamp` returns `max(low, min(value, high - 1))`, so this call would print `8`.

`test_calculator.py` defines `ClampTests` and dynamically adds test methods for its listed cases. Some expected values appear inconsistent with `clamp`’s implementation—for example, the case `(10, 0, 10, 10)` expects `10`, while `clamp` returns `9`.

The test command is `python -m unittest -v`. I did not run it.
