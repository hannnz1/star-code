"""Bounded project guidance; includes never expand workspace permissions."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from muse.permissions.policy import WorkspacePolicy
from muse.permissions.secrets import redact


def resource_text(path, root, maximum=48000):
    root = Path(root).absolute()
    for ancestor in [root, *root.parents]:
        if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
            raise PermissionError('Linked resource roots are unavailable')
    root, path = root.resolve(), Path(path).absolute()
    if not path.is_relative_to(root):
        raise PermissionError('Resource leaves workspace')
    cursor = root
    for part in path.relative_to(root).parts:
        cursor /= part
        if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
            raise PermissionError('Linked resources are unavailable')
    if not path.resolve(strict=True).is_relative_to(root) or path.stat().st_size > maximum:
        raise ValueError('Resource is outside workspace or too large')
    return path.read_bytes().decode('utf-8-sig')


def expand_guidance(content, directory, policy, *, depth=0, seen=None):
    seen = set() if seen is None else seen
    result, fenced = [], False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            fenced = not fenced
        if not fenced and stripped.startswith(('@./', '@../', '@/', '@~')):
            try:
                target = policy.resolve(str(directory / stripped[1:]), must_exist=True)
                if depth >= 5 or target in seen:
                    raise ValueError('Include depth or cycle limit')
                seen.add(target)
                boundary = policy.resource_boundary(target) if hasattr(policy, 'resource_boundary') else policy.root
                included = resource_text(target, boundary)
                result.append(expand_guidance(included, target.parent, policy, depth=depth + 1, seen=seen))
            except (OSError, ValueError):
                result.append('[Project include unavailable or denied]')
        else:
            result.append(line)
        if sum(map(len, result)) >= 48000:
            break
    return '\n'.join(result)[:48000]


class TrustedGuidancePolicy:
    def __init__(self, roots, private):
        self.policies = [WorkspacePolicy(root, private) for root in roots]
        self.root = self.policies[0].root

    def resource_boundary(self, path):
        for policy in self.policies:
            if path.is_relative_to(policy.root):
                return policy.root
        raise PermissionError('Include leaves explicit trusted sources')

    def resolve(self, path, *, must_exist=False):
        target = Path(path).absolute()
        boundary = self.resource_boundary(target)
        policy = next(policy for policy in self.policies if policy.root == boundary)
        return policy.resolve(str(target), must_exist=must_exist)


def project_guidance(context):
    if 'project_guidance' in context.cp:
        return context.cp['project_guidance']['content']
    root = context.workspace
    private = [context.settings.data_dir] + ([context.settings.config_path] if context.settings.config_path else [])
    policy = TrustedGuidancePolicy([root, *context.settings.instruction_roots], private)
    names = ['MEWCODE.md', 'STARCODE.md', 'AGENTS.md', 'MUSE.md', '.mewcode/MEWCODE.md', '.muse/MUSE.md']
    locations = [(directory / name, directory) for directory in context.settings.instruction_roots for name in names]
    locations += [(root / name, root) for name in names]
    current = WorkspacePolicy(root, private).resolve(context.cp.get('current_directory', '.'), must_exist=True)
    if not current.is_dir():
        raise ValueError('Current directory must be within the registered workspace')
    ancestors = list(reversed([current, *current.parents[:len(current.relative_to(root).parts)]]))
    for directory in ancestors:
        if directory != root:
            locations += [(directory / name, root) for name in names]
    locations += [(current / name, root) for name in ('MEWCODE.local.md', 'MUSE.local.md')]
    chunks, sources = [], []
    seen = set()
    for path, boundary in locations:
        try:
            if path.absolute() in seen:
                continue
            seen.add(path.absolute())
            source = resource_text(path, boundary)
            value = context.safe(expand_guidance(source, path.parent, policy))
            name = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            chunks.append(f'Project guidance {name}:\n{value}')
            sources.append({'path': name, 'sha256': hashlib.sha256(source.encode()).hexdigest(),
                            'expanded_sha256': hashlib.sha256(value.encode()).hexdigest(), 'order': len(sources)})
        except (OSError, ValueError):
            continue
    content = '\n\n'.join(chunks)[:48000]
    context.cp['project_guidance'] = {'content': content, 'sources': sources, 'version': context.cp.get('source_version', 1)}
    context.save()
    return content


def resource_snapshot(settings, request, workspace):
    from muse.extensions.roles import DurableRoles
    from muse.permissions.os_sandbox import snapshot
    secrets = [settings.access_token.get_secret_value()]
    if settings.provider:
        secrets.append(settings.provider.api_key.get_secret_value())
    ctx = SimpleNamespace(workspace=Path(workspace['path']), settings=settings,
                          cp={'current_directory': request.current_directory, 'source_version': 1},
                          safe=lambda value: redact(value, tuple(secrets)), save=lambda: None)
    project_guidance(ctx)
    DurableRoles(SimpleNamespace(context=ctx, register=lambda *args: None))
    ctx.cp['sandbox'] = snapshot(settings)
    return ctx.cp
