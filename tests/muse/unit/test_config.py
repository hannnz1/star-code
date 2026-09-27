import importlib.util
import json

import pytest


def config_module():
    assert importlib.util.find_spec("muse.config") is not None, "Configuration loader is not implemented"
    from muse import config
    return config


def test_existing_starcode_provider_is_loaded_without_exporting_secret(tmp_path):
    source = tmp_path / "starcode.yaml"
    source.write_text('providers:\n  - name: Legacy\n    protocol: openai-compat\n    base_url: https://model.example/v1\n    api_key: fixture-secret\n    model: fixture-model\nproxy:\n  enabled: false\n', encoding="utf-8")
    settings = config_module().load_settings(source, data_dir=tmp_path / "data")
    assert settings.provider.model == "fixture-model"
    assert settings.provider.api_key.get_secret_value() == "fixture-secret"
    assert "fixture-secret" not in json.dumps(settings.public(), ensure_ascii=False)
    assert source.read_text(encoding="utf-8").count("fixture-secret") == 1


def test_missing_provider_key_is_actionable(tmp_path, monkeypatch):
    monkeypatch.delenv("MUSE_API_KEY", raising=False)
    source = tmp_path / "settings.yaml"
    source.write_text("providers:\n  - model: test\n    base_url: https://example.com/v1\n    api_key_env: MUSE_MISSING_TEST_KEY\n", encoding="utf-8")
    with pytest.raises(ValueError, match="MUSE_MISSING_TEST_KEY"):
        config_module().load_settings(source, data_dir=tmp_path / "data")


def test_explicit_provider_selection_and_env_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSE_TEST_PROVIDER_KEY", "ephemeral-test-secret")
    source = tmp_path / "settings.yaml"
    source.write_text('providers:\n  - name: first\n    model: one\n    api_key: fake-first\n    base_url: https://one.example/v1\n  - name: second\n    model: two\n    api_key_env: MUSE_TEST_PROVIDER_KEY\n    base_url: https://two.example/v1\n', encoding="utf-8")
    settings = config_module().load_settings(source, provider_name="second", data_dir=tmp_path / "data")
    assert settings.provider.model == "two"
    assert settings.provider.api_key.get_secret_value() == "ephemeral-test-secret"
    assert "ephemeral-test-secret" not in repr(settings)


def test_model_override_keeps_selected_provider_and_source_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "starcode.yaml"
    original = ('providers:\n  - name: OpenAI\n    protocol: openai-responses\n'
                '    base_url: https://api.openai.com/v1\n    api_key_env: MUSE_TEST_PROVIDER_KEY\n'
                '    model: gpt-5.4-mini\n')
    source.write_text(original, encoding="utf-8")
    monkeypatch.setenv("MUSE_TEST_PROVIDER_KEY", "ephemeral-test-secret")
    monkeypatch.setenv("MUSE_MODEL", "gpt-6-luna")
    settings = config_module().load_settings(source, data_dir=tmp_path / "data")
    assert settings.provider.model == "gpt-6-luna"
    assert settings.provider.base_url == "https://api.openai.com/v1"
    assert settings.provider.api_key.get_secret_value() == "ephemeral-test-secret"
    assert source.read_text(encoding="utf-8") == original
    monkeypatch.delenv("MUSE_MODEL")
    assert config_module().load_settings(source, data_dir=tmp_path / "data").provider.model == "gpt-5.4-mini"


def test_no_implicit_legacy_import_or_openai_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-use-this")
    monkeypatch.delenv("MUSE_STARCODE_CONFIG", raising=False)
    monkeypatch.delenv("MUSE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = config_module().load_settings(data_dir=tmp_path / "data", require_provider=False)
    assert settings.provider is None
    assert settings.access_token.get_secret_value()


def test_data_token_is_stable_and_not_exported(tmp_path):
    config = config_module()
    first = config.load_settings(data_dir=tmp_path / "data", require_provider=False)
    second = config.load_settings(data_dir=tmp_path / "data", require_provider=False)
    assert first.access_token == second.access_token
    assert first.access_token.get_secret_value() not in json.dumps(first.public())
