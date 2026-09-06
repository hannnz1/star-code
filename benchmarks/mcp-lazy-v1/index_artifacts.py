"""Index retained local MCP evidence; no model calls and no credentials."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
files = set()
for name in ('mcp-full-current', 'mcp-schema-v1', 'mcp-selection-v1'):
    pointer = root / 'results' / (name + '-latest.txt')
    batch = root / pointer.read_text(encoding='utf-8').strip()
    assert batch.is_relative_to(root / 'results' / 'raw') and batch.is_dir()
    files.add(pointer)
    files.update(p for p in batch.rglob('*') if p.is_file())
for folder in ('mcp-lazy-v1', 'fixtures'):
    files.update(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for pattern in ('mcp-lazy-*', 'mcp-full-current-compile.log'):
    files.update(p for p in (root / 'results').glob(pattern) if p.is_file())
rows = [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
result = {'file_count': len(rows), 'total_bytes': sum(r['bytes'] for r in rows), 'files': rows,
          'raw_tracking': 'Raw directories are ignored by Git. Preserve these files with this index.'}
(root / 'results/mcp-validation-artifact-index.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
