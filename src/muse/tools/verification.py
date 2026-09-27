"""Conservative verification coverage for durable tool attempts."""


def mutation_ids(calls):
    # These tools only create managed records/artifacts. Children separately
    # pass the same completion gate. Even discovery can launch arbitrary code.
    exempt = {'verify_command', 'spawn_task', 'spawn_skill', 'spawn_worktree', 'team_message', 'team_work', 'save_artifact',
              'save_memory', 'delete_memory', 'install_skill'}
    return {call['id'] for call in calls
            if call['attempts'] > 0 and call['risk'] in {'write', 'execute'}
            and call['name'] not in exempt
            and not (call['name'].startswith('__hook_') and (call.get('result') or {}).get('metadata', {}).get('hook_child_id')
                     and call['arguments'].get('action_preview', {}).get('type') == 'agent')}
