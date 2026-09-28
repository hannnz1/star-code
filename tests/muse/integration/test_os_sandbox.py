import pytest
from test_permission_modes import setup

from muse.permissions.os_sandbox import SandboxError, sandbox_argv
from muse.tools.shell import run_command


async def test_windows_required_never_starts_command(tmp_path, monkeypatch):
    _, _, ctx, _ = setup(tmp_path)
    ctx.settings.sandbox_policy = 'required'
    monkeypatch.setattr('muse.permissions.os_sandbox.platform.system', lambda: 'Windows')
    called = []
    async def start(*args, **kwargs):
        called.append(args)
        raise AssertionError('Raw command started')
    monkeypatch.setattr('muse.tools.shell.asyncio.create_subprocess_exec', start)
    with pytest.raises(SandboxError, match='OS_SANDBOX_UNSUPPORTED'):
        await run_command(ctx, {'command': 'echo must not run'}, 'sandbox')
    assert not called


def test_linux_missing_backend_and_unenforceable_network_fail_closed(tmp_path, monkeypatch):
    _, _, ctx, _ = setup(tmp_path)
    ctx.settings.sandbox_policy = 'required'
    monkeypatch.setattr('muse.permissions.os_sandbox.platform.system', lambda: 'Linux')
    monkeypatch.setattr('muse.permissions.os_sandbox.shutil.which', lambda name: None)
    with pytest.raises(SandboxError, match='UNAVAILABLE'):
        sandbox_argv(ctx, ['bash', '-c', 'true'], tmp_path / 'temp')


def test_bwrap_uses_fresh_root_and_default_network_deny(tmp_path, monkeypatch):
    _, _, ctx, _ = setup(tmp_path)
    ctx.settings.sandbox_policy = 'required'
    monkeypatch.setattr('muse.permissions.os_sandbox.platform.system', lambda: 'Linux')
    monkeypatch.setattr('muse.permissions.os_sandbox.shutil.which', lambda name: '/usr/bin/bwrap')
    argv = sandbox_argv(ctx, ['bash', '-c', 'echo "raw"'], tmp_path / 'temp')
    assert '--unshare-all' in argv and '--die-with-parent' in argv
    assert ['--ro-bind', '/', '/'] not in [argv[index:index + 3] for index in range(len(argv))]
    assert argv[-3:] == ['bash', '-c', 'echo "raw"']
    ctx.settings.sandbox_policy = 'off'
    assert sandbox_argv(ctx, ['bash', '-c', 'echo "raw"'], tmp_path / 'temp') == argv


def test_seatbelt_profile_has_no_global_file_allow(tmp_path, monkeypatch):
    _, _, ctx, _ = setup(tmp_path)
    ctx.settings.sandbox_policy = 'required'
    monkeypatch.setattr('muse.permissions.os_sandbox.platform.system', lambda: 'Darwin')
    monkeypatch.setattr('muse.permissions.os_sandbox.shutil.which', lambda name: '/usr/bin/sandbox-exec')
    argv = sandbox_argv(ctx, ['bash', '-c', 'true'], tmp_path / 'temp')
    assert '(deny default)' in argv[2] and '(deny network*)' in argv[2]
    assert '(subpath "/")' not in argv[2]
