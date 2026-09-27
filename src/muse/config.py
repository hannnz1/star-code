"""Explicit configuration import; provider secrets never enter public settings."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, SecretStr


class ProviderSettings(BaseModel):
    name: str = "Model provider"
    protocol: str = "openai-responses"
    base_url: str
    model: str
    api_key: SecretStr = Field(exclude=True, repr=False)
    proxy_url: str | None = Field(default=None, exclude=True, repr=False)
    timeout: float = Field(default=120, gt=0)
    context_window: int = Field(default=128000, ge=4096)
    max_output_tokens: int = Field(default=8192, ge=256)
    thinking: bool = False


class Settings(BaseModel):
    data_dir: Path
    access_token: SecretStr = Field(exclude=True, repr=False)
    provider: ProviderSettings | None = None
    config_path: Path | None = None
    skill_roots: list[Path] = Field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = 8765
    max_turns: int = Field(default=40, ge=1, le=1000)
    max_tool_calls: int = Field(default=100, ge=1, le=10000)
    max_active_seconds: float = Field(default=900, gt=0)
    lease_seconds: float = Field(default=30, ge=1)
    heartbeat_seconds: float = Field(default=5, gt=0)
    allowed_origins: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:8765", "http://localhost:8765",
        "http://127.0.0.1:5173", "http://localhost:5173",
    ])
    browser_allowed_origins: list[str] = Field(default_factory=list)

    def public(self) -> dict:
        return self.model_dump(mode="json")


def _local_token(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "access-token"
    if target.is_symlink():
        raise ValueError("Access-token file must not be a symbolic link")
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(32))
        target.chmod(0o600)
    except FileExistsError:
        pass
    token = target.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("Local access-token file is empty")
    return token


def load_settings(
    config_path: str | Path | None = None,
    *,
    provider_name: str | None = None,
    data_dir: str | Path | None = None,
    require_provider: bool = True,
) -> Settings:
    explicit_path = config_path or os.getenv("MUSE_STARCODE_CONFIG") or os.getenv("MUSE_CONFIG")
    directory = Path(data_dir or os.getenv("MUSE_DATA_DIR", ".muse")).resolve()
    root: dict = {}
    source = Path(explicit_path).resolve() if explicit_path else None
    if source:
        try:
            root = yaml.safe_load(source.read_text(encoding="utf-8-sig")) or {}
        except (OSError, yaml.YAMLError):
            raise ValueError("Cannot read the selected configuration as YAML") from None
        if not isinstance(root, dict):
            raise ValueError("Configuration must be a YAML object")
    selected = None
    providers = root.get("providers", [])
    if providers:
        if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
            raise ValueError("providers must be a list of provider objects")
        name = provider_name or os.getenv("MUSE_PROVIDER")
        selected = next((p for p in providers if p.get("name") == name), None) if name else providers[0]
        if selected is None:
            raise ValueError("Selected provider is not present in the configuration")
    elif os.getenv("MUSE_API_KEY"):
        selected = {"name": "MUSE", "model": os.getenv("MUSE_MODEL", ""),
                    "base_url": os.getenv("MUSE_BASE_URL", "https://api.openai.com/v1"),
                    "api_key_env": "MUSE_API_KEY", "protocol": os.getenv("MUSE_PROTOCOL", "openai-responses")}

    provider = None
    if selected:
        key_env = selected.get("api_key_env")
        key = os.getenv(key_env, "") if key_env else selected.get("api_key", "")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Provider credential is missing: {key_env or 'api_key'}")
        protocol = selected.get("protocol", "openai-compat")
        if protocol == "openai":
            protocol = "openai-responses"
        if protocol not in {"openai-responses", "openai-compat", "anthropic"}:
            raise ValueError("Supported protocols: openai-responses, openai-compat, anthropic")
        base_url = str(selected.get("base_url", "")).rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Provider base_url must be an HTTP(S) URL without credentials or query")
        model = os.getenv("MUSE_MODEL") or selected.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Provider model is required")
        proxy = root.get("proxy") or {}
        proxy_url = None
        if proxy.get("enabled"):
            proxy_url = f"http://{proxy.get('host', '127.0.0.1')}:{int(proxy.get('port', 7890))}"
        provider = ProviderSettings(
            name=str(selected.get("name", "Model provider")), protocol=protocol,
            base_url=base_url, model=model.strip(), api_key=SecretStr(key),
            proxy_url=proxy_url, timeout=root.get("request_timeout_seconds", 120),
            context_window=selected.get("context_window", 128000),
            max_output_tokens=selected.get("max_output_tokens", 8192), thinking=selected.get("thinking", False),
        )
    elif require_provider:
        raise ValueError("Select a configuration with --config or MUSE_STARCODE_CONFIG; no model was configured")
    limits = root.get("agent") or {}
    skill_roots = root.get('skill_roots', [])
    if not isinstance(skill_roots, list) or any(not isinstance(value, str) or not value.strip() for value in skill_roots):
        raise ValueError('skill_roots must be a list of explicit directory paths')
    return Settings(
        data_dir=directory, access_token=SecretStr(_local_token(directory)), provider=provider,
        config_path=source, skill_roots=[(source.parent / value).resolve() for value in skill_roots] if source else [],
        max_turns=limits.get("max_turns", 40),
        max_tool_calls=limits.get("max_tool_calls", 100),
        max_active_seconds=limits.get("max_active_seconds", 900),
    )
