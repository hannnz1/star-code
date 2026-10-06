import sys

import pytest

from muse.openapi_types import main


def test_generation_uses_stable_bytes_and_detects_line_ending_drift(tmp_path, monkeypatch):
    (tmp_path / 'work').mkdir()
    (tmp_path / 'frontend/src').mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['openapi_types'])
    main()
    target = tmp_path / 'frontend/src/api.generated.ts'
    data = target.read_bytes()
    assert b'ImportedProducts' in data
    assert b'\r\n' not in data
    target.write_bytes(data.replace(b'\n', b'\r\n'))
    monkeypatch.setattr(sys, 'argv', ['openapi_types', '--check'])
    with pytest.raises(SystemExit, match='stale'):
        main()
