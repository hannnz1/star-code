I fixed `calculator.py` so all calculator tests pass.

Verification result:
- `python -m unittest -v`
- `test_calculator` passed
- `test_service` failed with `EXTERNAL_SERVICE_UNAVAILABLE`

Unresolved failure:
- `external_dependency.py` still returns `False`, and per your instruction I did not modify it.
- Therefore I cannot claim all tests passed.
