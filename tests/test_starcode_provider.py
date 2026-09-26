from mewcode.config import load_config


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
