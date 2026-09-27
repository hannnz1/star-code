Updated only `calculator.py`:

- Fixed `clamp` to use an inclusive upper bound:
  - from `min(value, high - 1)`
  - to `min(value, high)`

Result:
- `python -m unittest -v` passed
- 10/10 visible tests passed
- Exit code: 0

So the bug is fixed without changing tests or any other files.
