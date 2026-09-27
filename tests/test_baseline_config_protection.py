import pytest

from muse.permissions.policy import WorkspacePolicy


@pytest.mark.parametrize('name', ['config.yaml', 'permissions.local.yaml', 'skills/inspect.md'])
def test_baseline_configuration_is_protected_from_general_file_tools(tmp_path, name):
    policy = WorkspacePolicy(tmp_path)
    with pytest.raises(PermissionError, match='Sensitive'):
        policy.resolve('.mewcode/' + name)
