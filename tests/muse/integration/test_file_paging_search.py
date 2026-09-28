import asyncio
import json
import time
import uuid

import psutil
import pytest
from test_workspace_tools import context

from muse.contracts import ToolCall
from muse.tools.context import TaskControl


async def invoke(tools, name, **arguments):
    return await tools.execute(ToolCall(id=name + '-' + uuid.uuid4().hex, name=name, arguments=arguments))


def structured(tools, result):
    if result.metadata.get('offload_id'):
        _, content = tools.artifacts.read(result.metadata['offload_id'])
        return json.loads(content)
    return json.loads(result.content)


@pytest.mark.parametrize('data', [b'\xef\xbb\xbfFirst\r\n\xe4\xb8\xad\xe6\x96\x87\r\nLast', b'First\n\xe4\xb8\xad\xe6\x96\x87\nLast\n'])
async def test_file_paging_preserves_original_line_numbers_and_legacy_text(tmp_path, data):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.txt').write_bytes(data)
    legacy = await invoke(tools, 'read_file', path='file.txt')
    assert legacy.content == data.decode('utf-8-sig')
    page = await invoke(tools, 'read_file', path='file.txt', offset=0, limit=2)
    assert page.status == 'success'
    first = json.loads(page.content)
    assert first['lines'] == [{'line': 1, 'text': 'First'}, {'line': 2, 'text': '中文'}]
    assert first['next_offset'] == 2 and first['truncated'] is True
    final = json.loads((await invoke(tools, 'read_file', path='file.txt', offset=2, limit=2)).content)
    assert final['lines'] == [{'line': 3, 'text': 'Last'}]
    assert final['next_offset'] is None and final['truncated'] is False


@pytest.mark.parametrize('text,offset', [('', 0), ('one\n', 1), ('one\n', 100)])
async def test_empty_and_past_eof_pages(tmp_path, text, offset):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.txt').write_text(text, encoding='utf-8')
    result = await invoke(tools, 'read_file', path='file.txt', offset=offset)
    assert result.status == 'success'
    page = json.loads(result.content)
    assert page['lines'] == [] and page['next_offset'] is None and page['truncated'] is False


async def test_default_page_limit_and_limit_only_mode(tmp_path):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.txt').write_text('\n'.join(str(i) for i in range(2001)), encoding='utf-8')
    result = await invoke(tools, 'read_file', path='file.txt', offset=0)
    assert result.metadata['offload_id']
    page = structured(tools, result)
    assert len(page['lines']) == 2000 and page['next_offset'] == 2000
    page = json.loads((await invoke(tools, 'read_file', path='file.txt', limit=1)).content)
    assert page['lines'] == [{'line': 1, 'text': '0'}]


@pytest.mark.parametrize('options', [{'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 10001}, {'limit': 1.5}])
async def test_invalid_page_parameters_are_explicit(tmp_path, options):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.txt').write_text('one', encoding='utf-8')
    result = await invoke(tools, 'read_file', path='file.txt', **options)
    assert result.status == 'error' and result.error_code == 'INVALID_ARGUMENTS'


async def test_paging_still_refuses_outside_workspace_and_private_state(tmp_path):
    _, ctx, tools = context(tmp_path)
    outside = tmp_path / 'outside.txt'
    outside.write_text('private', encoding='utf-8')
    for path in [str(outside), str(ctx.settings.data_dir / 'state.db')]:
        result = await invoke(tools, 'read_file', path=path, offset=0, limit=1)
        assert result.status in {'denied', 'error'}
        assert 'private' not in result.content


@pytest.mark.parametrize('regex,case_sensitive,expected', [(False, False, [1, 2]), (False, True, [1]), (True, False, [1, 2]), (True, True, [1])])
async def test_search_case_and_regex_contract(tmp_path, regex, case_sensitive, expected):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.py').write_text('def A():\nDEF b():\nclass C:\n', encoding='utf-8')
    (ctx.workspace / 'ignored.txt').write_text('def ignored', encoding='utf-8')
    pattern = r'^def\s' if regex else 'def'
    result = await invoke(tools, 'search_text', pattern=pattern, glob='**/*.py', regex=regex, case_sensitive=case_sensitive)
    assert result.status == 'success'
    assert [match['line'] for match in json.loads(result.content)['matches']] == expected


async def test_old_search_remains_literal_and_invalid_regex_is_not_empty_success(tmp_path):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'file.txt').write_text('literal [ and ^def\\s\n', encoding='utf-8')
    legacy = await invoke(tools, 'search_text', pattern='[')
    assert len(json.loads(legacy.content)['matches']) == 1
    invalid = await invoke(tools, 'search_text', pattern='[', regex=True)
    assert invalid.status == 'error' and invalid.error_code == 'INVALID_ARGUMENTS'
    empty = await invoke(tools, 'search_text', pattern='not-here', regex=True)
    assert json.loads(empty.content)['matches'] == [] and empty.status == 'success'


async def test_search_reports_hit_and_candidate_limits(tmp_path, monkeypatch):
    from muse.tools import files
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'hits.txt').write_text('hit\n' * 101, encoding='utf-8')
    result = json.loads((await invoke(tools, 'search_text', pattern='hit', regex=True)).content)
    assert len(result['matches']) == 100 and result['truncated'] is True
    assert result['limits'] == {'candidate_files': 500, 'matches': 100, 'file_timeout_ms': 250, 'search_timeout_ms': 5000}
    for number in range(501):
        (ctx.workspace / f'empty-{number:03}.txt').write_text('', encoding='utf-8')
    # Isolate candidate count from slow filesystem timings; the real 5s deadline
    # is tested independently by the enumeration and catastrophic-regex probes.
    monkeypatch.setattr(files, 'SEARCH_TIMEOUT', 30)
    result = json.loads((await invoke(tools, 'search_text', pattern='nothing')).content)
    assert result['truncated'] is True and result['truncation_reason'] == 'candidate_limit'


async def test_catastrophic_regex_is_killed_and_worker_remains_responsive(tmp_path):
    _, ctx, tools = context(tmp_path)
    (ctx.workspace / 'bad.txt').write_text('a' * 100000 + '!', encoding='utf-8')
    started = time.monotonic()
    result = await asyncio.wait_for(invoke(tools, 'search_text', pattern=r'^(a+)+$', regex=True), timeout=8)
    assert result.status == 'error' and result.error_code == 'SEARCH_TIMEOUT'
    assert time.monotonic() - started < 7
    next_result = await invoke(tools, 'read_file', path='bad.txt', limit=1)
    assert next_result.status == 'success'


async def test_cancelled_search_leaves_no_regex_process(tmp_path):
    repo, ctx, tools = context(tmp_path)
    (ctx.workspace / 'bad.txt').write_text('a' * 100000 + '!', encoding='utf-8')
    search = asyncio.create_task(tools.files.search_text({'pattern': r'^(a+)+$', 'regex': True}, 'cancel-search'))
    child = None
    try:
        for _ in range(100):
            for process in psutil.Process().children():
                if 'muse.tools.regex_worker' in process.cmdline():
                    child = process
                    break
            if child is not None:
                break
            await asyncio.sleep(0.01)
        assert child is not None, 'The real regex subprocess must start'
        task = repo.get(ctx.task_id)
        repo.control(ctx.task_id, 'cancel', expected_revision=task.revision)
        with pytest.raises(TaskControl, match='CANCELLED'):
            await asyncio.wait_for(search, timeout=3)
        assert not child.is_running()
    finally:
        if not search.done():
            search.cancel()
        await asyncio.gather(search, return_exceptions=True)


async def test_pages_and_search_redact_multiline_secrets_without_changing_line_numbers(tmp_path):
    _, ctx, tools = context(tmp_path)
    body = 'synthetic-key-body-for-redaction-test'
    text = 'intro\n-----BEGIN PRIVATE KEY-----\n' + body + '\n-----END PRIVATE KEY-----\nafter\n'
    (ctx.workspace / 'key.txt').write_text(text, encoding='utf-8')
    page = structured(tools, await invoke(tools, 'read_file', path='key.txt', offset=2, limit=3))
    assert [row['line'] for row in page['lines']] == [3, 4, 5]
    assert page['lines'][-1]['text'] == 'after'
    assert body not in json.dumps(page)
    for regex in [False, True]:
        result = structured(tools, await invoke(tools, 'search_text', pattern='synthetic-key-body', regex=regex))
        assert result['matches'][0]['line'] == 3
        assert body not in json.dumps(result)


async def test_overflowing_regex_is_an_argument_error(tmp_path):
    _, _, tools = context(tmp_path)
    result = await invoke(tools, 'search_text', pattern='a{999999999999999999999999}', regex=True)
    assert result.status == 'error' and result.error_code == 'INVALID_ARGUMENTS'


async def test_candidate_enumeration_obeys_search_deadline(tmp_path, monkeypatch):
    from muse.tools import files
    _, ctx, tools = context(tmp_path)

    def slow_walk(*args, **kwargs):
        time.sleep(0.15)
        yield str(ctx.workspace), [], []

    monkeypatch.setattr(files.os, 'walk', slow_walk)
    monkeypatch.setattr(files, 'SEARCH_TIMEOUT', 0.03)
    started = time.monotonic()
    result = await invoke(tools, 'search_text', pattern='not-found', glob='*.py')
    assert result.status == 'error' and result.error_code == 'SEARCH_TIMEOUT'
    assert time.monotonic() - started < 0.12
