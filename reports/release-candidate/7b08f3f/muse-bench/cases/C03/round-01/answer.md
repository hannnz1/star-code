I fixed `calculator.py` so `clamp` now clamps to the upper bound inclusively.

Verification result:
- `python -m unittest -v` passed all calculator tests
- `test_service` still fails because `external_dependency.py` returns `False`, producing `EXTERNAL_SERVICE_UNAVAILABLE`

So the project is **not fully passing** due to the unresolved external dependency failure, and I’m not claiming all tests passed.
