I fixed `calculator.py` so the clamp logic now matches the tests.

Verification with exactly `python -m unittest -v`:
- `test_calculator` passes
- `test_service` still fails because `external_dependency.service_available()` returns `False`

So the project is **not fully passing** due to the unresolved external dependency failure, and I’m not claiming all tests passed.
