import subprocess
import json
from pathlib import Path
import pytest

from tests.muse.commerce.test_php_protocol import php  # noqa: F401


def test_theme_deploy_root_rejects_different_directory(php, tmp_path):  # noqa: F811
    public = tmp_path / 'public'
    private = tmp_path / 'private'
    for root in (public, private):
        (root / 'muse-storefront').mkdir(parents=True)
    script = tmp_path / 'target.php'
    script.write_text("<?php define('ABSPATH', __DIR__); require " + repr(str(Path(__file__).resolve().parents[3] / 'wordpress/muse-connector/includes/theme-deploy.php').replace('\\', '/')) + ";\n"
        + "define('MUSE_DEPLOY_THEME_ROOT', " + repr(str(private).replace('\\', '/')) + ");\n"
        + "function get_theme_root($name) { return " + repr(str(public).replace('\\', '/')) + "; }\n"
        + "function get_stylesheet_directory() { return get_theme_root('') . '/muse-storefront'; }\n"
        + "try { muse_connector_deploy_theme_target(); exit(1); } catch (RuntimeException $error) { exit(0); }", encoding='utf-8')
    result = subprocess.run([php, '-n', str(script)], capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('link,accepted', [('//evil/',False), ('///evil/',False), ('/shop/',True), ('/',True), ('#products',True)])
def test_php_static_theme_links_stay_on_current_host(php, tmp_path, link, accepted):
    script = tmp_path / 'static-link.php'
    target = Path(__file__).resolve().parents[3] / 'wordpress/muse-connector/includes/theme-deploy.php'
    script.write_text("<?php define('ABSPATH', __DIR__); require " + repr(str(target).replace('\\','/')) + ";\n"
        + "try { muse_connector_validate_static_file('templates/page.html', '<a href=\"' . json_decode(stream_get_contents(STDIN)) . '\">Shop</a>'); echo 'accepted'; } "
        + "catch (InvalidArgumentException $error) { echo 'rejected'; }", encoding='utf-8')
    result = subprocess.run([php, '-n', str(script)], input=json.dumps(link), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ('accepted' if accepted else 'rejected')


@pytest.mark.parametrize('link,accepted', [('//evil/a.png',False), ('/wp-content/uploads/muse-owned/project/image.png',True)])
def test_php_theme_settings_links_stay_on_current_host(php, tmp_path, link, accepted):
    target = Path(__file__).resolve().parents[3] / 'wordpress/muse-connector/includes/theme-deploy.php'
    script = tmp_path / 'settings-link.php'
    script.write_text("<?php define('ABSPATH', __DIR__); require " + repr(str(target).replace('\\','/')) + ";\n"
        + "try { muse_connector_validate_static_file('theme.json', json_encode(array('version'=>3, 'styles'=>array('background'=>array('backgroundImage'=>array('url'=>json_decode(stream_get_contents(STDIN)))))), JSON_UNESCAPED_SLASHES)); echo 'accepted'; } "
        + "catch (InvalidArgumentException $error) { echo 'rejected'; }", encoding='utf-8')
    result = subprocess.run([php, '-n', str(script)], input=json.dumps(link), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ('accepted' if accepted else 'rejected')


@pytest.mark.parametrize('link,accepted', [('//evil/',False), ('/shop/',True)])
def test_php_block_attribute_links_stay_on_current_host(php, tmp_path, link, accepted):
    target = Path(__file__).resolve().parents[3] / 'wordpress/muse-connector/includes/theme-deploy.php'
    script = tmp_path / 'block-link.php'
    script.write_text("<?php define('ABSPATH', __DIR__); require " + repr(str(target.parent / 'protocol.php').replace('\\','/')) + "; require "
        + repr(str(target).replace('\\','/')) + ";\n"
        + "try { muse_connector_validate_static_file('parts/header.html', '<!-- wp:navigation-link ' . json_encode(array('url'=>json_decode(stream_get_contents(STDIN)))) . ' /-->'); echo 'accepted'; } "
        + "catch (InvalidArgumentException $error) { echo 'rejected'; }", encoding='utf-8')
    result = subprocess.run([php, '-n', str(script)], input=json.dumps(link), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ('accepted' if accepted else 'rejected')

