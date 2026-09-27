"""Pinned GitHub archives, bounded extraction, and non-overwriting local install."""
import hashlib
import io
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import PurePosixPath

import httpx

LIMIT = 10 * 1024 * 1024


def validate_source(args):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args['repository']):
        raise ValueError('Repository must be owner/name')
    if not re.fullmatch(r'[a-fA-F0-9]{40}', args['commit']):
        raise ValueError('A full pinned Git commit is required')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', args['name']):
        raise ValueError('Invalid installation name')
    path = PurePosixPath(args['path'])
    if path.is_absolute() or '..' in path.parts or '\\' in args['path'] or ':' in args['path']:
        raise ValueError('Invalid skill path')
    return path


def install_archive(workspace, args, data):
    path = validate_source(args)
    if len(data) > LIMIT:
        raise ValueError('Skill archive exceeds limit')
    root = workspace.resolve()
    parent = root / '.muse/skills'
    for location in (root / '.muse', parent):
        if location.is_symlink() or (hasattr(location, 'is_junction') and location.is_junction()):
            raise ValueError('Skill installation path is linked')
    target = parent / args['name']
    if target.exists() or target.is_symlink():
        raise ValueError('Skill destination already exists')
    files, size = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if not parts or '..' in parts or member.filename.startswith('/') or '\\' in member.filename or ':' in member.filename:
                raise ValueError('Unsafe archive member')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Linked archive members are unsupported')
            relative = PurePosixPath(*parts[1:])
            if member.is_dir() or not relative.is_relative_to(path):
                continue
            relative = relative.relative_to(path)
            if not relative.parts or any(p.lower().startswith('.env') or p.lower() in {'.git', 'access-token', 'credentials.json'} for p in relative.parts):
                raise ValueError('Sensitive archive path')
            key = relative.as_posix()
            if key.casefold() in {p.casefold() for p in files}:
                raise ValueError('Duplicate archive filename')
            size += member.file_size
            if size > LIMIT or len(files) >= 500:
                raise ValueError('Expanded skill exceeds limit')
            files[key] = archive.read(member)
    if 'SKILL.md' not in files and not {'skill.yaml', 'prompt.md'}.issubset(files):
        raise ValueError('Selected path is not a skill directory')
    import yaml

    from mewcode.skills.parser import SkillParseError, parse_skill_text
    try:
        if 'skill.yaml' in files:
            meta = yaml.safe_load(files['skill.yaml'].decode('utf-8-sig'))
            if not isinstance(meta, dict):
                raise ValueError('Skill YAML must be a mapping')
            prompt = files['prompt.md'].decode('utf-8-sig').replace('\r\n', '\n')
            meta.setdefault('name', args['name'])
            if not meta.get('description'):
                meta['description'] = next((line.strip() for line in prompt.splitlines() if line.strip() and not line.startswith(('#', '---'))), '')
            source = '---\n' + yaml.safe_dump(meta) + '---\n' + prompt
        else:
            source = files['SKILL.md'].decode('utf-8-sig').replace('\r\n', '\n')
        if len(source.encode('utf-8')) > 256000:
            raise ValueError('Skill definition exceeds limit')
        skill = parse_skill_text(source, target / 'SKILL.md')
        if skill.name != args['name']:
            raise ValueError('Skill name must match the installation name')
    except (SkillParseError, yaml.YAMLError, KeyError) as error:
        raise ValueError('Invalid skill definition') from error
    parent.mkdir(parents=True, exist_ok=True)
    if parent.resolve() != parent or not parent.is_relative_to(root):
        raise ValueError('Skill installation path changed')
    from pathlib import Path
    staging = Path(tempfile.mkdtemp(prefix='.install-', dir=parent))
    try:
        for name, content in files.items():
            output = staging.joinpath(*PurePosixPath(name).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        if target.exists():
            raise ValueError('Skill destination already exists')
        os.rename(staging, target)
    finally:
        if staging.exists() and staging.resolve().parent == parent and not staging.is_symlink():
            shutil.rmtree(staging)
    return {'name': args['name'], 'repository': args['repository'], 'commit': args['commit'],
            'path': str(target.relative_to(root)), 'files': len(files), 'archive_sha256': hashlib.sha256(data).hexdigest()}


async def download_archive(args):
    validate_source(args)
    url = f"https://codeload.github.com/{args['repository']}/zip/{args['commit']}"
    async with (
        httpx.AsyncClient(timeout=60, trust_env=False, follow_redirects=False) as client,
        client.stream('GET', url) as response,
    ):
        response.raise_for_status()
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > LIMIT:
                raise ValueError('Skill archive exceeds limit')
    return bytes(data)
