from mewcode.config import load_config
from unittest.mock import patch
import pytest


def test_starcode_responses_alias_and_named_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('STAR_CODE_API_KEY', 'fixture-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'wrong-provider-key')
    path = tmp_path / 'provider.yaml'
    path.write_text('''providers:
  - name: Original
    protocol: openai-responses
    base_url: https://example.test/v1
    model: gpt-5.4-mini
    api_key_env: STAR_CODE_API_KEY
''', encoding='utf-8')
    provider = load_config(path).providers[0]
    assert provider.protocol == 'openai'
    assert provider.model == 'gpt-5.4-mini'
    assert provider.base_url == 'https://example.test/v1'
    assert provider.resolve_api_key() == 'fixture-key'
    assert 'fixture-key' not in repr(provider)


def test_missing_explicit_environment_never_uses_other_key(tmp_path, monkeypatch):
    monkeypatch.delenv('MISSING_STARCODE_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'wrong-provider-key')
    path = tmp_path / 'provider.yaml'
    path.write_text('''providers:
  - name: Original
    protocol: openai
    base_url: https://example.test/v1
    model: original-model
    api_key_env: MISSING_STARCODE_KEY
''', encoding='utf-8')
    assert load_config(path).providers[0].resolve_api_key() == ''


def test_selected_config_preserves_transport_and_limits(tmp_path, monkeypatch):
    path = tmp_path / 'original.yaml'
    path.write_text('''request_timeout_seconds: 17
proxy:
  enabled: true
  host: 127.0.0.1
  port: 7899
agent:
  max_turns: 7
  max_tool_calls: 12
  max_active_seconds: 90
providers:
  - name: Original
    protocol: openai-responses
    base_url: https://example.test/v1
    model: original-model
    api_key_env: STAR_CODE_API_KEY
''', encoding='utf-8')
    monkeypatch.setenv('STAR_CODE_API_KEY', 'fixture')
    monkeypatch.setenv('MUSE_STARCODE_CONFIG', str(path))
    config = load_config()
    assert config.agent_limits.max_turns == 7
    assert config.agent_limits.max_tool_calls == 12
    assert config.agent_limits.max_active_seconds == 90
    from mewcode.client import create_client
    with patch('mewcode.client.AsyncOpenAI') as sdk:
        client = create_client(config.providers[0])
        kwargs = sdk.call_args.kwargs
        assert kwargs['timeout'] == 17
        assert kwargs['max_retries'] == 0
        assert client.limits.max_turns == 7
        assert config.providers[0].proxy_url == 'http://127.0.0.1:7899'


@pytest.mark.parametrize('value', [23, ['KEY'], True])
def test_invalid_credential_environment_rejected(tmp_path, value):
    import yaml
    from mewcode.config import ConfigError
    path = tmp_path / 'invalid.yaml'
    path.write_text(yaml.safe_dump({'providers': [{'name': 'p', 'protocol': 'openai',
        'base_url': 'https://example.test', 'model': 'model', 'api_key_env': value}]}))
    with pytest.raises(ConfigError, match='api_key_env'):
        load_config(path)
