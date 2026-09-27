import asyncio
from types import SimpleNamespace

import pytest

from benchmarks.run import run


def test_existing_campaign_is_rejected_before_fixture_or_api_start(tmp_path, monkeypatch):
    old = tmp_path / 'summary.json'
    old.write_text('original evidence', encoding='utf-8')
    def forbidden(*args, **kwargs):
        pytest.fail('started fixture server before rejecting reused campaign')
    monkeypatch.setattr('benchmarks.run.ThreadingHTTPServer', forbidden)
    with pytest.raises(FileExistsError):
        asyncio.run(run(SimpleNamespace(output=str(tmp_path), rounds=3, cases=None, config='unused')))
    assert old.read_text(encoding='utf-8') == 'original evidence'
