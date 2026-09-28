"""Explicit public projection; private checkpoints are never exported."""
import json

from muse.memory.maintenance import MemoryMaintenance
from muse.permissions.secrets import redact


def task_trace(repository, settings, task_id):
    repository.get(task_id)
    with repository.db.engine.connect() as conn:
        root = repository._root_id(conn, task_id)
        identifiers = repository._group_ids(conn, root)
    jobs = MemoryMaintenance(repository, settings).jobs()
    tasks = []
    for identifier in identifiers:
        task = repository.get(identifier)
        links = repository.db.rows('SELECT parent_id FROM task_delegations WHERE child_id=:id', {'id': identifier})
        events = []
        while len(events) < 10000:
            page = repository.events(identifier, after=events[-1]['sequence'] if events else 0)
            events.extend(page)
            if len(page) < 500:
                break
        tasks.append({'id': identifier, 'parent_id': links[0]['parent_id'] if links else None,
            'followup_parent_id': task.parent_task_id,
            'status': task.status, 'workspace_id': task.workspace_id, 'coordinator_mode': task.coordinator_mode,
            'permission_mode': task.permission_mode, 'policy_version': task.policy_version,
            'plan': {'task_id': task.plan_task_id, 'sha256': task.plan_sha256, 'user_request': task.prompt} if task.plan_task_id else None,
            'tools': repository.calls(identifier), 'approvals': repository.approvals(identifier),
            'events': events, 'events_truncated': len(events) >= 10000,
            'maintenance': [job for job in jobs if job['task_id'] == identifier],
            'usage': task.checkpoint.get('usage'), 'recall_mode': task.checkpoint.get('memory_recall_mode')})
    secrets = [settings.access_token.get_secret_value()]
    if settings.provider:
        secrets.append(settings.provider.api_key.get_secret_value())
    def public(value):
        if isinstance(value, dict):
            return {key: public(child) for key, child in value.items()
                    if key not in {'provider_states', '_protocol_state', 'protocol_state', 'encrypted_content', 'signature', 'proxy_url', 'api_key', 'snapshot'} }
        if isinstance(value, list):
            return [public(child) for child in value]
        return redact(value, tuple(secrets)) if isinstance(value, str) else value
    return public({'schema_version': 1, 'root_id': root, 'tasks': tasks,
                   'duration_clock': 'tool.elapsed_seconds uses monotonic clock; event timestamps use wall clock'})


def trace_jsonl(trace):
    return '\n'.join(json.dumps({'schema_version': trace['schema_version'], 'root_id': trace['root_id'], **task}, ensure_ascii=False)
                     for task in trace['tasks']) + '\n'
