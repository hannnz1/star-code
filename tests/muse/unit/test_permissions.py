import importlib.util
from pathlib import Path

import pytest


def policy(root):
    assert importlib.util.find_spec("muse.permissions") is not None, "Workspace policy is missing"
    from muse.permissions.policy import WorkspacePolicy
    return WorkspacePolicy(root)


@pytest.mark.parametrize("filename", ["../outside.txt", ".env", ".env.local", "credentials.json", ".git/config", ".muse/access-token"])
def test_workspace_policy_rejects_traversal_and_sensitive_files(tmp_path, filename):
    p = policy(tmp_path)
    with pytest.raises(PermissionError):
        p.resolve(filename)


def test_workspace_policy_accepts_chinese_and_space_paths(tmp_path):
    folder = tmp_path / "项目 文件"
    folder.mkdir()
    target = folder / "说明.txt"
    target.write_text("资料", encoding="utf-8")
    assert policy(tmp_path).resolve("项目 文件/说明.txt") == target.resolve()


def test_symlink_cannot_escape_workspace(tmp_path):
    root = tmp_path / "workspace"
    outside = tmp_path / "external"
    root.mkdir()
    outside.mkdir()
    (outside / "sentinel.txt").write_text("private", encoding="utf-8")
    p = policy(root)
    if __import__("os").name == "nt":
        import subprocess
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "link"), str(outside)], capture_output=True)
        assert completed.returncode == 0, "Cannot establish Windows junction test fixture"
    else:
        (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        p.resolve("link/sentinel.txt")


def test_redaction_hides_literal_secrets_and_private_keys():
    assert importlib.util.find_spec("muse.permissions") is not None
    from muse.permissions.secrets import redact, contains_secret
    raw = 'api_key: sk-fixture-private-value\nAuthorization: Bearer abcdef1234567890\nnormal: value'
    assert contains_secret(raw)
    safe = redact(raw)
    assert "sk-fixture-private-value" not in safe
    assert "abcdef1234567890" not in safe
    assert "normal: value" in safe


def test_workspace_replaced_by_junction_before_policy_creation_is_rejected(tmp_path):
    import os
    import subprocess
    from muse.permissions.policy import WorkspacePolicy
    root=tmp_path/'registered-project'
    outside=tmp_path/'outside'
    root.mkdir();outside.mkdir();(outside/'sentinel.txt').write_text('private')
    # Simulates replacement of an already registered workspace before a new worker starts.
    root.rmdir()
    if os.name=='nt':
        subprocess.run(['cmd','/c','mklink','/J',str(root),str(outside)],check=True,capture_output=True)
    else:root.symlink_to(outside,target_is_directory=True)
    with pytest.raises(PermissionError):
        WorkspacePolicy(root).resolve('sentinel.txt',must_exist=True)
