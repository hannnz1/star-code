"""Bounded project guidance; includes never expand workspace permissions."""
import hashlib
from pathlib import Path

from muse.permissions.policy import WorkspacePolicy


def resource_text(path, root, maximum=48000):
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
                included = resource_text(target, policy.root)
                result.append(expand_guidance(included, target.parent, policy, depth=depth + 1, seen=seen))
            except (OSError, ValueError):
                result.append('[Project include unavailable or denied]')
        else:
            result.append(line)
        if sum(map(len, result)) >= 48000:
            break
    return '\n'.join(result)[:48000]


def project_guidance(context):
    if 'project_guidance' in context.cp:
        return context.cp['project_guidance']['content']
    root = context.workspace
    policy = WorkspacePolicy(root, [context.settings.data_dir] + ([context.settings.config_path] if context.settings.config_path else []))
    names = ['MEWCODE.md', 'STARCODE.md', 'AGENTS.md', 'MUSE.md',
             '.mewcode/MEWCODE.md', '.muse/MUSE.md', 'MEWCODE.local.md', 'MUSE.local.md']
    chunks, sources = [], []
    for name in names:
        try:
            source = resource_text(root / name, root)
            value = context.safe(expand_guidance(source, (root / name).parent, policy))
            chunks.append(f'Project guidance {name}:\n{value}')
            sources.append({'path': name, 'sha256': hashlib.sha256(source.encode()).hexdigest()})
        except (OSError, ValueError):
            continue
    content = '\n\n'.join(chunks)[:48000]
    context.cp['project_guidance'] = {'content': content, 'sources': sources}
    context.save()
    return content
