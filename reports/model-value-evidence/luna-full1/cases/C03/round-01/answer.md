Fixed `calculator.py` so `clamp` includes the upper bound; all 10 calculator tests pass.

The requested verification command, `python -m unittest -v`, still fails: `test_service` reports `EXTERNAL_SERVICE_UNAVAILABLE` because `external_dependency.service_available()` returns `False`. I left `external_dependency.py` and the tests unchanged. **All tests do not pass.**
