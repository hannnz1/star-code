"""Recheck a saved local gate against current sources, classes and distributable."""
import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(run):
    raw = ROOT / 'benchmarks/results/raw/feature-parity-v1' / run
    record = json.loads((raw / 'validation.json').read_text(encoding='utf-8-sig'))
    manifest = json.loads((raw / 'source-manifest.json').read_text(encoding='utf-8-sig'))
    expected = {name.replace('\\', '/'): value.lower() for name, value in manifest.items()}
    actual = {p.relative_to(ROOT).as_posix(): digest(p) for p in (ROOT / 'src').rglob('*') if p.is_file()}
    if expected != actual:
        raise RuntimeError('Current source set or bytes differ from the tested snapshot')
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for path in (raw / 'test-results').glob('TEST-*.xml'):
        suite = ET.parse(path).getroot()
        for key in counts:
            counts[key] += int(suite.attrib.get(key, 0))
    if record['status'] != 'PASS' or counts != record['tests'] or counts['tests'] < 233 or any(counts[k] for k in ('failures', 'errors', 'skipped')):
        raise RuntimeError('Saved full test gate is not a verified pass')
    jar = ROOT / 'build/libs/star-code.jar'
    if digest(jar) != record['jar_sha256'].lower():
        raise RuntimeError('Distributable no longer matches the accepted run')
    matched = []
    with zipfile.ZipFile(jar) as archive:
        names = archive.namelist()
        for folder in (ROOT / 'build/classes/java/main', ROOT / 'src/main/resources'):
            for path in sorted(folder.rglob('*')):
                if not path.is_file():
                    continue
                name = path.relative_to(folder).as_posix()
                if names.count(name) != 1 or archive.read(name) != path.read_bytes():
                    raise RuntimeError('Packaged content mismatch: ' + name)
                matched.append(name)
        packaged = {n for n in names if n.startswith('com/starcode/') and n.endswith('.class')}
        compiled = {n for n in matched if n.startswith('com/starcode/') and n.endswith('.class')}
        if not compiled or compiled != packaged:
            raise RuntimeError('Production class set mismatch')
    git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
    head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(git + ['status', '--porcelain', '--', 'src'], cwd=ROOT, text=True).strip())
    result = dict(status='PASS', scope='local tests and package integrity only', run_id=run,
                  verified_at=datetime.now(timezone.utc).isoformat(), tests=counts,
                  source_files=len(actual), source_manifest_sha256=digest(raw / 'source-manifest.json'),
                  matching_classes=len(compiled), matching_resources=len(matched)-len(compiled),
                  jar_sha256=digest(jar), jar_bytes=jar.stat().st_size, current_git_head=head,
                  tested_source_uncommitted=dirty, test_run_git_head=record['git_commit'],
                  full_feature_parity='NOT_VERIFIED', performance_parity='NOT_VERIFIED',
                  real_provider_interoperability='NOT_VERIFIED', network_model_calls=0)
    target = ROOT / 'benchmarks/results/feature-parity-accepted.json'
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    verify(parser.parse_args().run)
