"""Explicit configuration import; provider secrets never enter public settings."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)


class CommerceConnectorSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service_url: str
    token: SecretStr = Field(exclude=True, repr=False, min_length=16)
    versions_lock_path: Path

    @field_validator('service_url')
    @classmethod
    def fixed_service_url(cls, value):
        url = urlsplit(value)
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or url.path not in {'', '/'} or (url.scheme != 'https' and not
                    (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}))):
            raise ValueError('Connector requires HTTPS or a loopback service without URL credentials')
        _ = url.port
        return value.rstrip('/')


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
    thinking_capability: Literal['unsupported', 'openai-reasoning', 'anthropic-manual', 'anthropic-adaptive'] = 'unsupported'
    reasoning_effort: Literal['low', 'medium', 'high', 'xhigh', 'max'] = 'medium'
    thinking_budget_tokens: int = Field(default=2048, ge=1024)
    thinking_summary: bool = True


class Settings(BaseModel):
    commerce_max_active_plans: int = Field(default=2, ge=1, le=20, strict=True)
    data_dir: Path
    access_token: SecretStr = Field(exclude=True, repr=False)
    provider: ProviderSettings | None = None
    commerce_connector: CommerceConnectorSettings | None = Field(default=None, exclude=True, repr=False)
    config_path: Path | None = None
    skill_roots: list[Path] = Field(default_factory=list)
    instruction_roots: list[Path] = Field(default_factory=list)
    agent_roots: list[Path] = Field(default_factory=list)
    worktree_managed_root: Path | None = None
    memory_auto_extract: bool = False
    memory_auto_consolidate: bool = False
    memory_semantic_recall: bool = False
    memory_budget_tokens: int = Field(default=0, ge=0)
    memory_max_requests: int = Field(default=8, ge=0, le=1000)
    memory_recall_top_k: int = Field(default=10, ge=1, le=10)
    sandbox_policy: Literal['off', 'required'] = 'off'
    sandbox_runtime_roots: list[Path] = Field(default_factory=list)
    sandbox_network_allowlist: list[str] = Field(default_factory=list)
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
            thinking_capability=selected.get('thinking_capability', 'unsupported'),
            reasoning_effort=selected.get('reasoning_effort', 'medium'),
            thinking_budget_tokens=selected.get('thinking_budget_tokens', 2048),
            thinking_summary=selected.get('thinking_summary', True),
        )
    elif require_provider:
        raise ValueError("Select a configuration with --config or MUSE_STARCODE_CONFIG; no model was configured")
    limits = root.get("agent") or {}
    skill_roots = root.get('skill_roots', [])
    if not isinstance(skill_roots, list) or any(not isinstance(value, str) or not value.strip() for value in skill_roots):
        raise ValueError('skill_roots must be a list of explicit directory paths')
    worktrees = root.get('worktrees') or {}
    trusted = {}
    for key in ('instruction_roots', 'agent_roots'):
        values = root.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f'{key} must be a list of explicit directories')
        trusted[key] = [((source.parent if source else Path.cwd()) / value).absolute() for value in values]
    if not isinstance(worktrees, dict):
        raise ValueError('worktrees must be a configuration object')  # noqa: TRY004 -- configuration errors use ValueError at the CLI boundary.
    managed_root = worktrees.get('managed_root')
    if managed_root is not None:
        if not isinstance(managed_root, str) or not managed_root.strip():
            raise ValueError('worktrees.managed_root must be an explicit directory path')
        managed_root = ((source.parent if source else Path.cwd()) / managed_root).absolute()
    connector = None
    commerce_limits = root.get('commerce') or {}
    if not isinstance(commerce_limits, dict):
        raise ValueError('commerce must be a configuration object')
    if root.get('commerce_connector') is not None:
        value = root['commerce_connector']
        if (not isinstance(value, dict) or set(value) != {'service_url', 'token_env', 'versions_lock_path'}
                or not isinstance(value['token_env'], str) or not isinstance(value['versions_lock_path'], str)):
            raise ValueError('commerce_connector requires service_url, token_env and versions_lock_path')
        try:
            connector = CommerceConnectorSettings(service_url=value['service_url'],
                token=SecretStr(os.getenv(value['token_env'], '')),
                versions_lock_path=((source.parent if source else Path.cwd()) / value['versions_lock_path']).resolve())
        except (ValidationError, ValueError, TypeError):
            raise ValueError('Invalid commerce connector configuration or missing service credential') from None
    return Settings(
        data_dir=directory, access_token=SecretStr(_local_token(directory)), provider=provider,
        config_path=source, skill_roots=[(source.parent / value).resolve() for value in skill_roots] if source else [],
        commerce_connector=connector,
        commerce_max_active_plans=commerce_limits.get('max_active_plans', 2),
        worktree_managed_root=managed_root,
        **trusted,
        sandbox_policy=(root.get('sandbox') or {}).get('policy', 'off'),
        sandbox_runtime_roots=[Path(value).absolute() for value in (root.get('sandbox') or {}).get('runtime_roots', [])],
        sandbox_network_allowlist=(root.get('sandbox') or {}).get('network_allowlist', []),
        **{f'memory_{name}': value for name, value in (root.get('memory') or {}).items()
           if name in {'auto_extract', 'auto_consolidate', 'semantic_recall', 'budget_tokens', 'max_requests', 'recall_top_k'}},
        max_turns=limits.get("max_turns", 40),
        max_tool_calls=limits.get("max_tool_calls", 100),
        max_active_seconds=limits.get("max_active_seconds", 900),
    )
