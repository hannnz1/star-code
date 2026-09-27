"""Reproducible Java behavior inventory. Mapping is not a passing test result."""
import csv
import json
import re
from pathlib import Path

from build_migration_inventory import JAVA, OUT, TARGET

# Each contract names the active implementation, executable evidence and the
# deliberate semantic replacement. Baseline-only tests never prove public entry parity.
CONTRACTS = {
    'agent': ('src/muse/agent;src/muse/tasks/worker.py', 'tests/muse/unit/test_agent_loop.py;tests/muse/unit/test_agent_completion.py;tests/test_active_group_budget.py',
              'Durable sequential tool rounds, shared limits, cancellation and verified completion replace the in-process loop. No dontAsk permission bypass or parallel write dispatch.'),
    'command': ('src/muse/terminal.py;src/muse/compat_cli.py', 'tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py',
                'Slash commands use the shared HTTP task service. Rewind files and conversation are explicit separate actions. Worktree mutations and skill execution are approved task tools, not direct slash side effects.'),
    'config': ('src/muse/config.py;mewcode/config.py', 'tests/test_starcode_provider.py;tests/muse/unit/test_config.py;tests/test_baseline_config_protection.py',
               'Preserve original model, endpoint, proxy, credential source and limits. Explicit missing environment keys never fall back to another provider.'),
    'context': ('src/muse/agent/context.py;src/muse/tools/registry.py', 'tests/muse/unit/test_context.py;tests/test_terminal_context.py;tests/test_context.py;tests/test_context_window.py',
                'Deterministic complete-turn compaction and durable offloads replace model-written tagged summaries. Java summary-tag/retry parser is intentionally not in the active execution path.'),
    'hook': ('src/muse/extensions/hooks.py;src/muse/agent/loop.py', 'tests/test_durable_hooks.py;tests/test_hook_lifecycle.py;tests/test_async_hook_job.py;tests/test_extension_receipts.py;tests/test_hooks.py',
             'Configured events use durable receipts, approvals and child jobs. Startup/shutdown mean task-runtime boundaries; shell/HTTP hooks require approval. No unapproved global hooks.'),
    'instructions': ('src/muse/agent/instructions.py', 'tests/test_project_guidance.py',
                     'Registered workspace instructions and bounded includes are snapshotted. Implicit home/ancestor traversal is removed to preserve the workspace boundary.'),
    'llm': ('src/muse/providers;src/muse/tasks/conversation.py', 'tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py',
            'Responses, Chat Completions and Anthropic structured streams require terminal evidence. Durable checkpoints preserve complete exchanges; public errors omit provider response secrets.'),
    'mcp': ('src/muse/extensions/mcp.py;src/muse/extensions/stdio.py;mewcode/mcp/client.py', 'tests/test_durable_mcp.py;tests/test_mcp_http_integration.py;tests/test_mcp_transport_safety.py;tests/test_mcp_pagination.py;tests/test_mcp.py',
            'Lazy explicit configured-server discovery, bounded schemas and separately approved calls replace automatic readOnly remote execution. HTTP/stdio real local fixtures cover transport; model never grants remote authority.'),
    'memory': ('src/muse/memory/service.py;src/muse/extensions/memory.py', 'tests/test_durable_memory_tools.py;tests/muse/integration/test_artifacts_documents_memory.py;tests/test_memory.py',
               'User/project SQLite memories replace Markdown index authority and implicit asynchronous model writes. Save/delete are explicit approved tools; secret and scope checks remain enforced.'),
    'permission': ('src/muse/permissions;src/muse/tasks/repository.py', 'tests/muse/unit/test_permissions.py;tests/test_permissions.py;tests/muse/integration/test_workspace_tools.py;tests/test_review_regressions.py',
                   'Workspace deny rules and digest-bound per-action approvals replace reusable broad command grants and bypass modes. Windows process containment is not an OS filesystem/network sandbox. File-symlink clean-host gate remains open.'),
    'prompt': ('src/muse/agent/instructions.py;src/muse/agent/loop.py', 'tests/test_project_guidance.py;tests/test_durable_roles.py;tests/muse/unit/test_agent_completion.py;tests/muse/unit/test_provider_stream.py',
               'Deterministic role/task instructions, selected memories and tool restrictions replace Java prompt modules. No model/provider override through skill or role metadata.'),
    'session': ('src/muse/tasks;src/muse/storage;src/muse/tools/files.py', 'tests/test_conversation_checkpoints.py;tests/test_state_backup.py;tests/muse/integration/test_reconciliation.py;tests/muse/integration/test_migration.py;tests/muse/integration/test_crash_process.py',
                'Transactional SQLite events/checkpoints and hash-checked file journals replace JSONL session authority. Damaged/unknown effects are retained for explicit reconciliation, never silently skipped or replayed.'),
    'skill': ('src/muse/extensions/skills.py;src/muse/extensions/skill_install.py', 'tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py',
              'Lazy Markdown/YAML skills, explicit global skill_roots, source-bound fork and pinned archive installation. Selected original model is mandatory; conflicting provider metadata is rejected.'),
    'subagent': ('src/muse/extensions/roles.py;src/muse/tasks/delegation.py', 'tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py',
                 'Builtin/project roles and isolated role work inherit capability intersections and shared budgets. All children are persistent tasks; foreground blocking and tmux runner spawning are replaced by task waiting/review.'),
    'task': ('src/muse/tasks;src/muse/extensions/teams.py', 'tests/test_durable_delegation.py;tests/test_durable_teams.py;tests/test_extension_receipts.py;tests/muse/integration/test_recovery.py',
             'Persisted queue, lease fencing, child IDs, messages, automatic parent wakeup and cancellation replace in-memory task futures. Client timeout leaves work running.'),
    'team': ('src/muse/tasks/teams.py;src/muse/extensions/teams.py;src/muse/tasks/delegation.py', 'tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py',
             'Root-task groups, SQLite inbox/board, revisions/dependencies and persisted children replace team directories, file locks and pane backends. Terminal/web view the same group; no separate teammate CLI authority.'),
    'tool': ('src/muse/tools;src/muse/permissions', 'tests/muse/integration/test_workspace_tools.py;tests/test_shell_lifecycle.py;tests/test_mutation_verification.py;tests/test_edit_file.py;tests/muse/integration/test_shell_runtime.py',
             'Bounded file/search/edit/command tools share one dispatch and approval path. Structured exit codes, process-tree cancellation and verification prevent false success. Unsupported OS sandbox is not claimed.'),
    'ui': ('src/muse/tui.py;src/muse/terminal.py;frontend/src/main.tsx', 'tests/test_durable_tui.py;tests/test_terminal_service.py;tests/test_terminal_context.py;tests/muse/integration/test_frontend.py;tests/test_commands.py',
           'Textual terminal and React workspace replace Java terminal rendering. Original slash concepts remain discoverable; Windows paths stay in JSON/argv rather than shell interpolation.'),
    'worktree': ('src/muse/extensions/worktrees.py', 'tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py',
                 'Exact-commit sibling checkout, role restrictions, reviewed fast-forward merge and clean merged retirement. No copying private ignored files, auto-running local hooks, auto-deleting work, or implicit conflict merge.'),
    'starcode': ('src/muse/cli.py;src/muse/compat_cli.py;pyproject.toml;hatch_build.py', 'tests/test_compat_entry.py;tests/test_distribution_integration.py;tests/muse/integration/test_launcher.py',
                 'Python console/module entry plus API/Worker replace JVM/Gradle launch. Wheel bundles the web UI. Independent no-JVM Windows acceptance remains pending.'),
}

def category(path):
    parts = path.relative_to(JAVA).parts
    index = parts.index('starcode')
    return parts[index + 1] if len(parts) > index + 2 else 'starcode'

def main():
    production = sorted(JAVA.glob('src/main/java/**/*.java'))
    tests = sorted(JAVA.glob('src/test/java/**/*.java'))
    rows, test_rows = [], []
    lines = ['# Java behavior and assertion audit', '',
             'This inventory maps behavior contracts, not identical implementations. Baseline tests are retained as helper evidence; active durable tests are listed first. Passing counts come only from the linked JUnit run, never from this generator.', '',
             'The clean Windows/no-JVM/file-symlink release gate is still open. Changed contracts below are explicit replacements, not claims of Java option or UI identity.', '']
    for name, (implementation, evidence, contract) in CONTRACTS.items():
        for path in implementation.split(';') + evidence.split(';'):
            if not (TARGET / path).exists():
                raise ValueError(f'Missing mapped path: {path}')
        lines += [f'## {name}', '', contract, '', f'Active implementation: `{implementation}`', '', f'Regression files: `{evidence}`', '']
    for path in production:
        name = category(path)
        implementation, evidence, contract = CONTRACTS[name]
        rows.append([path.relative_to(JAVA).as_posix(), name, implementation, evidence, 'MAPPED_CONTRACT_RELEASE_GATE_OPEN', contract])
    for path in tests:
        name = category(path)
        _, evidence, contract = CONTRACTS[name]
        source = path.read_text(encoding='utf-8-sig')
        methods = re.findall(r'@(?:Test|ParameterizedTest)(?:\([^)]*\))?[\s\S]*?\bvoid\s+(\w+)\s*\(', source)
        # Test support files legitimately contain no @Test method.
        test_rows.append([path.relative_to(JAVA).as_posix(), ';'.join(methods), evidence, contract,
                          'KEY_ASSERTIONS_MAPPED' if methods else 'TEST_SUPPORT_REPLACED_BY_PYTEST_FIXTURES'])
        lines += [f'### {path.name}', '', 'Key assertion intents: ' + (', '.join(f'`{m}`' for m in methods) or 'Shared Git test support.'), '', f'Evidence: `{evidence}`', '']
    for filename, header, values in [
        ('java-migration-matrix.csv', ['java_source', 'module', 'python_implementation', 'regression_files', 'status', 'contract'], rows),
        ('java-test-matrix.csv', ['java_test', 'key_assertions', 'python_regressions', 'contract', 'status'], test_rows),
    ]:
        with (OUT / filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(header); writer.writerows(values)
    (OUT / 'java-behavior-audit.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'production_files': len(rows), 'test_files': len(test_rows), 'test_intents': sum(len(row[1].split(';')) for row in test_rows if row[1]), 'release_accepted': False}))

if __name__ == '__main__':
    main()
