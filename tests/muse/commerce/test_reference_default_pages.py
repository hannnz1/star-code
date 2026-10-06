import json
import subprocess
from pathlib import Path

import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


@pytest.mark.parametrize('wrong_slug', [False, True])
def test_only_fresh_woocommerce_pages_are_moved_out_of_reserved_slugs(php, tmp_path, wrong_slug):  # noqa: F811
    source = (Path(__file__).resolve().parents[3] / 'src/muse/commerce/assets/reference/bootstrap.php').read_text()
    function = source.split("ini_set('display_errors'", 1)[0]
    script = tmp_path / 'pages.php'
    script.write_text(function + '''
$updates = array();
function wc_get_page_id($kind) { return array('shop'=>5, 'cart'=>6, 'checkout'=>7)[$kind]; }
function get_post($id) { global $wrong; return (object)array('ID'=>$id, 'post_type'=>'page',
    'post_name'=>($wrong && $id === 6) ? 'merchant-content' : array(5=>'shop',6=>'cart',7=>'checkout')[$id]); }
function wp_update_post($data, $error) { global $updates; $updates[]=$data; return $data['ID']; }
function is_wp_error($value) { return false; }
''' + '$wrong=' + ('true' if wrong_slug else 'false') + ''';
try { muse_reference_move_default_pages(); echo json_encode($updates); }
catch (Throwable $error) { echo json_encode($updates); exit(2); }
''', encoding='utf-8')
    result = subprocess.run([php, '-n', str(script)], capture_output=True, text=True, timeout=10, check=False)
    if wrong_slug:
        assert result.returncode == 2
        # Validate the whole set before modifying even the first page.
        assert json.loads(result.stdout) == []
    else:
        assert result.returncode == 0
        updates = json.loads(result.stdout)
        assert [item['post_name'] for item in updates] == [f'muse-reference-default-{kind}' for kind in ('shop', 'cart', 'checkout')]
        assert all(item['post_status'] == 'draft' for item in updates)
