"""Optional platform backend; failure never launches the unwrapped command."""
import json
import platform
import shutil
from pathlib import Path


class SandboxError(ValueError):
    pass


def capabilities():
    system = platform.system()
    name = {'Linux': 'bwrap', 'Darwin': 'sandbox-exec'}.get(system)
    executable = shutil.which(name) if name else None
    return {'platform': system, 'backend': name, 'executable': executable,
            'available': bool(executable), 'validated': False,
            'reason': None if executable else 'OS_SANDBOX_UNAVAILABLE' if name else 'OS_SANDBOX_UNSUPPORTED',
            'network_allowlist_supported': False}


def snapshot(settings):
    return {'policy': settings.sandbox_policy, 'capability': capabilities(),
            'runtime_roots': [str(path.absolute()) for path in settings.sandbox_runtime_roots],
            'network_allowlist': settings.sandbox_network_allowlist}


def sandbox_argv(context, argv, temp):
    policy = context.cp.setdefault('sandbox', snapshot(context.settings))
    if policy['policy'] == 'off':
        return argv
    capability = policy['capability']
    current = capabilities()
    if not capability['available'] or not current['available']:
        raise SandboxError(capability['reason'] or current['reason'] or 'OS_SANDBOX_UNAVAILABLE')
    if current['backend'] != capability['backend'] or current['executable'] != capability['executable']:
        raise SandboxError('OS_SANDBOX_BACKEND_CHANGED')
    if policy['network_allowlist']:
        raise SandboxError('OS_SANDBOX_NETWORK_ALLOWLIST_UNSUPPORTED')
    workspace = context.workspace.resolve(strict=True)
    runtime = [Path(path) for path in ['/usr', '/bin', '/sbin', '/lib', '/lib64', '/System/Library', '/Library/Apple/System/Library', *policy['runtime_roots']]]
    runtime = list(dict.fromkeys(str(path.resolve()) for path in runtime if path.exists()))
    if any(Path(path) == Path(Path(path).anchor) or path in {'/', ''} for path in runtime):
        raise SandboxError('OS_SANDBOX_RUNTIME_ROOT_TOO_BROAD')
    private = [context.settings.data_dir.absolute()]
    if context.settings.config_path:
        private.append(context.settings.config_path.absolute())
    temp = Path(temp).absolute()
    if workspace == workspace.parent or any(workspace == path or workspace.is_relative_to(path) for path in private):
        raise SandboxError('OS_SANDBOX_WORKSPACE_UNSAFE')
    if capability['backend'] == 'bwrap':
        wrapped = [capability['executable'], '--unshare-all', '--die-with-parent', '--new-session',
                   '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
        for path in runtime:
            wrapped += ['--ro-bind', path, path]
        for path in ('/etc/ld.so.cache', '/etc/ld.so.conf'):
            if Path(path).is_file():
                wrapped += ['--ro-bind', path, path]
        wrapped += ['--bind', str(workspace), str(workspace), '--bind', str(temp), str(temp)]
        for path in private:
            if path.is_relative_to(workspace) or any(path.is_relative_to(Path(root)) for root in runtime):
                if path.is_dir():
                    wrapped += ['--tmpfs', str(path)]
                elif path.exists():
                    wrapped += ['--ro-bind', '/dev/null', str(path)]
        return [*wrapped, '--chdir', str(workspace), '--', *argv]
    rules = ['(version 1)', '(deny default)', '(allow process-exec)', '(allow process-fork)', '(allow sysctl-read)', '(deny network*)']
    for path in [*runtime, str(workspace), str(temp)]:
        rules.append('(allow file-read* (subpath ' + json.dumps(path) + '))')
    for path in (str(workspace), str(temp)):
        rules.append('(allow file-write* (subpath ' + json.dumps(path) + '))')
    rules += ['(allow file-read* file-write* (literal "/dev/null"))', '(allow file-read* (literal "/dev/urandom"))']
    for path in private:
        rules.append('(deny file-read* file-write* (subpath ' + json.dumps(str(path)) + '))')
    return [capability['executable'], '-p', '\n'.join(rules), *argv]
