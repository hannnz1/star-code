"""Task policy decisions shared by dispatcher and durable execution boundary."""
import hashlib
import json


def requires_approval(mode, risk):
    return risk == 'execute' or (risk == 'write' and mode == 'default')


def action_digest(task, name, arguments):
    identity = [task['id'], task['workspace_id'], name, arguments]
    # Preserve already-issued v8 approvals under the unchanged, frozen legacy
    # policy. Any explicit user policy change leaves this compatibility path.
    if not task['legacy_policy']:
        identity.extend([task['permission_mode'], task['policy_version']])
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()
