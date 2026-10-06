import copy

import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import ApprovalGrant, ChangeOperation
from muse.commerce_connector.authorization import ExecutionAuthority
from muse.commerce_connector.operations import validate_operation
from muse.commerce_connector.wordpress import WordPressConnection


def connection(url='https://store.example'):
    return WordPressConnection('connection', 'project', 'staging', url, 'service', 'not-a-real-key')


def page():
    return ChangeOperation(operation_id='op-1', kind='update_owned_page', resource_key='page:12',
                           expected_fingerprint='a' * 64, payload={'page_id': 12, 'title': 'About', 'content': 'Merchant text'})


def grant():
    return ApprovalGrant(id='grant-1', changeset_digest='b' * 64, project_id='project', environment='staging',
                         resource_preconditions={'page:12': 'a' * 64}, verification_hash='c' * 64, expires_at=1900)


def test_valid_authorization_matches_full_operation_and_current_approval():
    authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1000)
    token = authority.issue(grant(), connection(), page())
    assert authority.verify(token, grant(), connection(), page()) == page()
    assert 'Merchant text' not in token


@pytest.mark.parametrize('change', ['target', 'rebound-target', 'environment', 'payload', 'precondition', 'revoked', 'verification', 'digest', 'expiry', 'future', 'signature'])
def test_changed_scope_or_expired_authorization_is_rejected(change):
    authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1000)
    approval, operation, target = grant(), page(), connection()
    token = authority.issue(approval, target, operation)
    if change == 'target':
        target = WordPressConnection('another', 'project', 'staging', 'https://other.example', 'service', 'not-real')
    elif change == 'rebound-target':
        target = connection('https://other.example')
    elif change == 'environment':
        approval = approval.model_copy(update={'environment': 'live'})
    elif change == 'payload':
        operation = operation.model_copy(update={'payload': {'page_id': 12, 'title': 'Changed', 'content': 'Merchant text'}})
    elif change == 'precondition':
        approval = approval.model_copy(update={'resource_preconditions': {'page:12': 'd' * 64}})
    elif change == 'revoked':
        approval = approval.model_copy(update={'status': 'revoked'})
    elif change == 'verification':
        approval = approval.model_copy(update={'verification_hash': 'd' * 64})
    elif change == 'digest':
        approval = approval.model_copy(update={'changeset_digest': 'd' * 64})
    elif change == 'expiry':
        authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1900)
    elif change == 'future':
        authority = ExecutionAuthority(b'k' * 32, clock=lambda: 999)
    elif change == 'signature':
        authority = ExecutionAuthority(b'q' * 32, clock=lambda: 1000)
    with pytest.raises(CommerceFailure):
        authority.verify(token, approval, target, operation)


@pytest.mark.parametrize('mutation', ['extra', 'resource', 'no-precondition', 'bool-id', 'script', 'url', 'nonfinite'])
def test_fixed_operation_contract_rejects_unsafe_or_ambiguous_inputs(mutation):
    operation = page().model_dump()
    if mutation == 'extra':
        operation['payload']['sql'] = 'DROP TABLE'
    elif mutation == 'resource':
        operation['resource_key'] = 'page:13'
    elif mutation == 'no-precondition':
        operation['expected_fingerprint'] = None
    elif mutation == 'bool-id':
        operation['payload']['page_id'] = True
    elif mutation == 'script':
        operation['payload']['content'] = '<script>alert(1)</script>'
    elif mutation == 'url':
        operation['payload']['content'] = '<a href="https://evil.example">click</a>'
    elif mutation == 'nonfinite':
        operation['payload']['title'] = float('nan')
    with pytest.raises(CommerceFailure):
        validate_operation(ChangeOperation(**operation))


@pytest.mark.parametrize('token', ['', 'x' * 8193, 'a.b', 'eyJzZWNyZXQiOiJhYmMifQ.invalid'])
def test_invalid_token_has_sanitized_failure(token):
    with pytest.raises(CommerceFailure) as error:
        ExecutionAuthority(b'k' * 32, clock=lambda: 1000).verify(token, grant(), connection(), page())
    assert 'abc' not in str(error.value)


def test_signing_does_not_accept_expired_or_excessively_long_grant():
    authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1000)
    for expiry in (999, 2801, float('nan'), float('inf')):
        approval = grant().model_copy(update={'expires_at': expiry})
        with pytest.raises(CommerceFailure):
            authority.issue(approval, connection(), page())


def test_nested_input_is_not_modified_by_validation():
    operation = page()
    before = copy.deepcopy(operation.model_dump())
    assert validate_operation(operation) == operation
    assert operation.model_dump() == before

@pytest.mark.parametrize('case', ['huge-issued', 'deep-json'])
def test_signed_malformed_tokens_fail_closed_without_runtime_exception(case):
    import base64
    import hmac
    import json
    authority = ExecutionAuthority(b'k' * 32, clock=lambda: 1000)
    if case == 'deep-json':
        raw = ('[' * 3000 + '0' + ']' * 3000).encode()
    else:
        valid = authority.issue(grant(), connection(), page())
        body = valid.split('.')[0]
        claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        claims['issued_at'] = 10 ** 400
        raw = json.dumps(claims).encode()
    token = base64.urlsafe_b64encode(raw).rstrip(b'=').decode() + '.' + base64.urlsafe_b64encode(hmac.digest(b'k' * 32, raw, 'sha256')).rstrip(b'=').decode()
    assert len(token) < 8192
    with pytest.raises(CommerceFailure):
        authority.verify(token, grant(), connection(), page())

