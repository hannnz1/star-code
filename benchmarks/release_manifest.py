"""Reproducible source identity and conservative acceptance accounting. No credentials."""
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
CASES = [f'{prefix}{i:02}' for prefix in 'RDCBP' for i in range(1, 5)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(output: Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'manifest.json'
    if path.exists():
        raise FileExistsError(path)
    files = [ROOT / name for name in ('pyproject.toml', 'uv.lock', 'hatch_build.py', 'frontend/package-lock.json')]
    files.extend(ROOT.glob('*.ps1'))
    for directory in ('src/muse', 'mewcode', 'benchmarks', 'frontend/src', 'tests'):
        files.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py', '.json', '.yaml', '.ts', '.tsx', '.css'})
    if not files or any(not p.is_file() for p in files):
        raise ValueError('Required source/lockfile missing')
    def git(*args):
        result = subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', *args], cwd=ROOT, capture_output=True, check=True)
        return result.stdout
    data = {'format': 1, 'source_root': str(ROOT), 'head': git('rev-parse', 'HEAD').decode().strip(),
            'tracked_patch_sha256': hashlib.sha256(git('diff', 'HEAD', '--binary')).hexdigest(),
            'files': {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(files))},
            'python': sys.version, 'platform': platform.platform(),
            'dependencies': sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions() if d.metadata['Name']),
            'planned_attempts': 60, 'order': [{'round': r, 'case': c} for r in range(1, 4) for c in CASES],
            'human_review': 'PENDING', 'independent_windows': 'PENDING',
            'config': 'Original StarCode provider; credentials and raw configuration excluded',
            'cost': None}
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    return path


def verify_manifest(path: Path) -> bool:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for name, digest in data['files'].items():
        target = ROOT / name
        if not target.resolve().is_relative_to(ROOT) or not target.is_file() or sha256(target) != digest:
            raise ValueError(f'Source changed or missing: {name}')
    return True


def record_settings(path, settings):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    provider = settings.provider
    endpoint = urlsplit(provider.base_url)
    data['effective_settings'] = {
        'provider': provider.name, 'model': provider.model, 'protocol': provider.protocol,
        'endpoint': urlunsplit((endpoint.scheme, endpoint.hostname + (':' + str(endpoint.port) if endpoint.port else ''), endpoint.path, '', '')),
        'context_window': provider.context_window, 'max_output_tokens': provider.max_output_tokens,
        'timeout': provider.timeout, 'thinking': provider.thinking,
        'max_turns': settings.max_turns, 'max_tool_calls': settings.max_tool_calls,
        'max_active_seconds': settings.max_active_seconds}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def acceptance(records):
    indexed = {}
    for record in records:
        key = (record['round'], record['case'])
        if key in indexed:
            raise ValueError(f'Duplicate attempt: {key}')
        if key[0] not in range(1, 4) or key[1] not in CASES:
            raise ValueError(f'Unexpected attempt: {key}')
        indexed[key] = record
    slots = [indexed.get((r, c), {'result': 'NOT_RUN'}) for r in range(1, 4) for c in CASES]
    return {'planned': 60, 'completed': len(indexed),
            'missing': sum(row['result'] == 'NOT_RUN' for row in slots),
            'pending_human': sum(row['result'] == 'AUTO_PASS_REVIEW_REQUIRED' for row in slots),
            'failed_or_blocked': sum(row['result'] in {'FAIL', 'BLOCKED'} for row in slots),
            # Independent environment and signed semantic review are separate gates.
            'release_gate': 'NOT_ACCEPTED'}
