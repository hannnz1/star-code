"""Immutable execution capabilities; prose files only influence instructions."""
import hashlib
from importlib.resources import files

ROLE_TOOLS = {
    'store_manager': {'read_commerce_context', 'commerce_status', 'submit_blueprint',
                      'dispatch_commerce_step', 'request_commerce_review', 'ask_user', 'team_status'},
    'product_content': {'read_commerce_context', 'commerce_status', 'submit_product_drafts', 'ask_user'},
    # Fixed static code operations do not grant host Shell or general file access.
    'site_developer': {'read_commerce_context', 'commerce_status', 'submit_blueprint', 'ask_user',
                       'read_theme_file', 'write_theme_file', 'show_theme_diff', 'seal_theme_code', 'read_conflict_file'},
}
for tools in ROLE_TOOLS.values():
    tools.add('read_offload')  # Existing handler verifies task ownership and reads bounded slices.
DELEGATION_CEILING = sorted(set().union(*ROLE_TOOLS.values()))


def role_snapshot():
    result = {}
    for name in ROLE_TOOLS:
        body = files('muse.commerce').joinpath('agents', name + '.md').read_text(encoding='utf-8')
        result[name] = {'body': body, 'sha256': hashlib.sha256(body.encode()).hexdigest()}
    return result


def allows(context, name):
    role = context.cp.get('role')
    if role not in ROLE_TOOLS:
        return True
    return bool(context.cp.get('commerce')) and name in ROLE_TOOLS[role]


def prompt_from_snapshot(snapshot, role, prompt):
    item = snapshot['commerce'][role]
    if hashlib.sha256(item['body'].encode()).hexdigest() != item['sha256']:
        raise ValueError('Commerce role snapshot digest differs')
    return item['body'] + '\n\nTask and untrusted merchant data:\n' + prompt
