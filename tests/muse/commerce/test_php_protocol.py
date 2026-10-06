import base64
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from muse.commerce.models import ApprovalGrant, ChangeOperation
from muse.commerce.repository import digest
from muse.commerce_connector.authorization import ExecutionAuthority
from muse.commerce_connector.wordpress import WordPressConnection

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def php():
    executable = os.environ.get('MUSE_TEST_PHP') or shutil.which('php')
    portable = ROOT / 'work/tools/php-8.4.26/php.exe'
    if executable is None and portable.exists():
        executable = str(portable)
    if executable is None:
        pytest.skip('PHP CLI required for actual cross-language protocol tests')
    return executable


def run(php, value):
    extensions = ['-d', 'extension_dir=' + str(Path(php).parent / 'ext'), '-d', 'extension=zip'] if value['mode'] == 'theme' else []
    process = subprocess.run([php, '-n', *extensions, str(ROOT / 'tests/fixtures/commerce/php-protocol.php'),
                              str(ROOT / 'wordpress/muse-connector/includes/protocol.php')],
                             input=json.dumps(value, ensure_ascii=True), capture_output=True, text=True, timeout=10, check=False)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize('value', [{}, [], {'b': [], 'a': {}}, {'中文': '值/\u2028😀', 'a': [1, True, None]},
                                  {'price': '19.99', 'nested': {'stock': 3, 'name': 'Cup'}}])
def test_php_canonical_digest_matches_python_without_losing_object_shape(php, value):
    assert run(php, {'mode': 'canonical', 'data': value})['digest'] == digest(value)


@pytest.fixture
def authorized():
    operation = ChangeOperation(operation_id='op-1', kind='update_owned_page', resource_key='page:12',
                                expected_fingerprint='b' * 64, payload={'page_id': 12, 'title': '中文😀', 'content': 'Cup'})
    grant = ApprovalGrant(id='grant', project_id='project', environment='staging', changeset_digest='c' * 64,
                          resource_preconditions={'page:12': 'b' * 64, 'settings': 'd' * 64},
                          verification_hash='e' * 64, expires_at=2800)
    connection = WordPressConnection('connection', 'project', 'staging', 'https://store.example', 'user', 'fixture')
    secret = b'x' * 32
    token = ExecutionAuthority(secret, clock=lambda: 1000).issue(grant, connection, operation)
    return {'mode': 'verify', 'operation': operation.model_dump(mode='json'), 'token': token,
            'secret': base64.b64encode(secret).decode(), 'now': 1000,
            'scope': {'project_id': 'project', 'connection_id': 'connection', 'environment': 'staging',
                      'target_url': 'https://store.example'}}


def test_php_accepts_exact_python_permit(php, authorized):
    assert run(php, authorized) == {'accepted': True, 'grant_id': 'grant'}


@pytest.mark.parametrize('change', ['secret', 'signature', 'expiry', 'future', 'project_id', 'connection_id',
                                   'environment', 'target_url', 'operation_id', 'payload', 'fingerprint',
                                   'resource', 'kind', 'extra', 'token_size'])
def test_php_rejects_tampered_or_mismatched_permits(php, authorized, change):
    value = copy.deepcopy(authorized)
    if change == 'secret': value['secret'] = base64.b64encode(b'y' * 32).decode()
    elif change == 'signature': value['token'] = value['token'][:-1] + ('A' if value['token'][-1] != 'A' else 'B')
    elif change == 'expiry': value['now'] = 2800
    elif change == 'future': value['now'] = 999
    elif change in value['scope']: value['scope'][change] = 'wrong'
    elif change == 'operation_id': value['operation']['operation_id'] = 'other'
    elif change == 'payload': value['operation']['payload']['title'] = 'Changed'
    elif change == 'fingerprint': value['operation']['expected_fingerprint'] = 'f' * 64
    elif change == 'resource': value['operation']['resource_key'] = 'page:13'
    elif change == 'kind': value['operation']['kind'] = 'publish_owned_page'
    elif change == 'extra': value['operation']['extra'] = 'injected'
    else: value['token'] = 'x' * 8193
    assert run(php, value) == {'accepted': False}


def theme_payload():
    from muse.commerce.models import SiteBrief, StoreSnapshot
    from muse.commerce.site import build_site_blueprint
    from muse.commerce.theme import build_site_archive
    blueprint = build_site_blueprint(SiteBrief(brand_name='Fixture', language='en-US', currency='USD'),
                                     StoreSnapshot(project_id='project', environment='staging'))
    metadata, archive = build_site_archive(blueprint, [], code_revision='a' * 40)
    return {'package': metadata.model_dump(mode='json'), 'archive_base64': base64.b64encode(archive).decode()}


def test_php_accepts_actual_deterministic_theme_archive(php):
    assert run(php, {'mode': 'theme', 'payload': theme_payload()}) == {'accepted': True, 'files': 15}


@pytest.mark.parametrize('attack', ['path', 'php', 'javascript', 'event', 'css_url', 'duplicate', 'manifest', 'hash'])
def test_php_rejects_archive_attacks_even_with_matching_package_hash(php, attack):
    payload = theme_payload()
    if attack == 'hash':
        payload['package']['package_sha256'] = 'e' * 64
    elif attack == 'manifest':
        payload['package']['files_manifest'][0]['sha256'] = 'e' * 64
    else:
        archive = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload['archive_base64']))) as old, zipfile.ZipFile(archive, 'w') as new:
            for item in old.infolist():
                content = old.read(item.filename)
                if attack == 'path' and item.filename.endswith('style.css'): item.filename = '../style.css'
                if attack == 'php' and item.filename.endswith('functions.php'): content = b'<?php echo "bad";'
                if item.filename.endswith('templates/page.html'):
                    if attack == 'javascript': content = b'<script>alert(1)</script>'
                    if attack == 'event': content = b'<p onclick="alert(1)">Bad</p>'
                if attack == 'css_url' and item.filename.endswith('assets/storefront.css'): content = b'body {background:url(https://evil.example)}'
                new.writestr(item, content)
                if attack == 'duplicate' and item.filename.endswith('style.css'): new.writestr(item, content)
                for record in payload['package']['files_manifest']:
                    if item.filename == 'muse-storefront/' + record['path']:
                        record.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        raw = archive.getvalue()
        payload['archive_base64'] = base64.b64encode(raw).decode()
        payload['package']['package_sha256'] = hashlib.sha256(raw).hexdigest()
    assert run(php, {'mode': 'theme', 'payload': payload}) == {'accepted': False}
