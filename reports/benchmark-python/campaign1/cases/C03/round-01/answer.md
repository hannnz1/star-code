I fixed `calculator.py` so all calculator tests pass.

Verification result:
- `python -m unittest -v` ran successfully for `test_calculator`
- `test_service` still fails because `external_dependency.service_available()` returns `False`

Unresolved failure:
- `EXTERNAL_SERVICE_UNAVAILABLE` in `test_service.py`

I did not modify `external_dependency.py`, per your instruction, so I cannot claim all tests passed.
