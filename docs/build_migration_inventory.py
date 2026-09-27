"""Read-only source inventory; excludes local configuration and credentials."""
import csv
import hashlib
import json
from pathlib import Path


JAVA = Path('C:/Users/Administrator/Desktop/project/star code')
BASELINE = Path('C:/Users/Administrator/Desktop/project/mewcode-python')
OUT = Path(__file__).resolve().parent
TARGET = OUT.parent
MAPPING = {
    'agent': ('mewcode/agent.py;src/muse/agent', 'Durable Worker and public legacy entry integrated; full option/command parity pending'),
    'context': ('mewcode/context;src/muse/agent/context.py', 'Compaction and command parity pending'),
    'config': ('mewcode/config.py;src/muse/config.py', 'Original provider compatibility tested; real acceptance pending'),
    'llm': ('mewcode/client.py;src/muse/providers', 'Protocol fixtures tested; live matrix pending'),
    'tool': ('mewcode/tools;src/muse/tools', 'Core tools integrated; extension verification added'),
    'permission': ('mewcode/permissions;src/muse/permissions', 'Durable approvals integrated; clean Windows symlink gate pending'),
    'session': ('mewcode/session.py;src/muse/tasks', 'Durable tasks integrated; conversation rewind parity pending'),
    'memory': ('mewcode/memory;src/muse/memory', 'Both implementations present; semantic convergence pending'),
    'instructions': ('mewcode/memory/instructions.py;src/muse/agent', 'Instruction precedence acceptance pending'),
    'prompt': ('mewcode/prompts.py;src/muse/agent', 'Prompt behavior equivalence pending'),
    'command': ('mewcode/commands;src/muse/terminal.py', 'Partial durable terminal commands; full command matrix pending'),
    'ui': ('mewcode/app.py;src/muse/tui.py;frontend', 'Durable Textual/web and legacy entry integrated; full command/UI parity pending'),
    'mcp': ('mewcode/mcp;src/muse/extensions/mcp.py', 'Durable stdio tested; HTTP and cancellation acceptance pending'),
    'skill': ('mewcode/skills;src/muse/extensions/skills.py', 'Markdown/YAML and reload tested; install/global roots/model parity pending'),
    'hook': ('mewcode/hooks;src/muse/extensions/hooks.py', 'Partial durable events; async/all event parity pending'),
    'subagent': ('mewcode/agents;src/muse/tasks/delegation.py;src/muse/extensions/roles.py', 'Durable builtin roles and inherited tool restrictions tested; custom role parity pending'),
    'task': ('mewcode/agents/task_manager.py;src/muse/tasks', 'Durable queue/spawn receipt/shared budget tested; additional extension reconciliation pending'),
    'worktree': ('mewcode/worktree;src/muse/extensions/worktrees.py', 'Durable exact-commit child checkout tested; merge/lifecycle parity pending'),
    'team': ('mewcode/teams;src/muse/extensions/teams.py;src/muse/tasks/teams.py', 'Durable scoped inbox/status tested; shared board/coordinator lifecycle pending'),
}


def main():
    manifest = []
    for label, root, files in [
        ('starcode', JAVA, JAVA.glob('src/**/*.java')),
        ('mewcode-python', BASELINE, (BASELINE / 'mewcode').rglob('*.py')),
    ]:
        for path in sorted(files):
            manifest.append({'source': label, 'path': path.relative_to(root).as_posix(),
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (OUT / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    with (OUT / 'java-migration-matrix.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['java_source', 'module', 'python_candidates', 'existing_candidates', 'acceptance_status', 'remaining_gate'])
        sources = sorted(JAVA.glob('src/main/java/**/*.java'))
        for path in sources:
            relative = path.relative_to(JAVA).as_posix()
            module = path.parent.name
            candidates, gate = MAPPING.get(module, ('mewcode/__main__.py;src/muse/cli.py', 'Entry point convergence and no-JVM release pending'))
            existing = ';'.join(item for item in candidates.split(';') if (TARGET / item).exists())
            writer.writerow([relative, module, candidates, existing, 'NOT_FULLY_ACCEPTED', gate])
    print(f'{len(sources)} Java production files mapped; {len(manifest)} source hashes recorded')


if __name__ == '__main__':
    main()
