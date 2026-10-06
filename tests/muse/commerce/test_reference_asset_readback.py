import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


@pytest.mark.parametrize('attack', ['none', 'changed', 'traversal', 'private_path', 'scoped_package', 'variable_font'])
def test_actual_php_reads_exact_installed_assets_and_rejects_wrong_bytes_or_private_paths(php, tmp_path, attack):  # noqa: F811
    target = tmp_path / 'wp-content/plugins/woocommerce/woocommerce.php'
    target.parent.mkdir(parents=True)
    content = b'<?php /* Fixed offline plugin */'
    target.write_bytes(content)
    row = {'path': 'wp-content/plugins/woocommerce/woocommerce.php',
           'sha256': hashlib.sha256(content).hexdigest(), 'byte_size': len(content)}
    if attack in {'scoped_package', 'variable_font'}:
        row['path'] = 'wp-content/plugins/woocommerce/' + (
            'assets/client/blocks/@woocommerce/stores/store-notices.js' if attack == 'scoped_package'
            else 'assets/fonts/Inter-VariableFont_slnt,wght.woff2')
        target = tmp_path / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if attack == 'changed': target.write_bytes(content + b' changed')
    if attack == 'traversal': row['path'] = 'wp-content/plugins/woocommerce/../../../wp-config.php'
    if attack == 'private_path': row['path'] = 'wp-content/mu-plugins/000-muse-reference-config.php'
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([php, '-n', str(root / 'src/muse/commerce/assets/reference/verify-assets.php'), str(tmp_path)],
        input=json.dumps([row]), capture_output=True, text=True, timeout=10, check=False)
    if attack in {'none', 'scoped_package', 'variable_font'}:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == [row]
    else:
        assert result.returncode == 2
        assert result.stdout == '' and result.stderr.strip() == 'REFERENCE_ASSET_READBACK_REJECTED'
