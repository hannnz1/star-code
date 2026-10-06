"""Unverified or conflicting deployment inputs must never start a store."""
import importlib.util

import pytest


def environment_module():
    assert importlib.util.find_spec('muse.commerce'), 'Commerce environment preflight is missing'
    from muse.commerce import environment
    return environment


def lock():
    return {'images': {'wordpress': 'wordpress@sha256:' + 'a' * 64,
                       'database': 'mariadb@sha256:' + 'b' * 64,
                       'cli': 'wordpress@sha256:' + 'c' * 64},
            'wordpress': '7.1.2', 'woocommerce': '11.1.2',
            'verified': True}


def test_unverified_images_refuse_before_any_container_start():
    module = environment_module()
    value = lock()
    value['verified'] = False
    with pytest.raises(ValueError, match='verified'):
        module.validate_lock(value)
    for image in ['wordpress:latest', 'wordpress:7.1.2', 'wordpress@sha256:bad']:
        value = lock()
        value['images']['wordpress'] = image
        with pytest.raises(ValueError, match='digest'):
            module.validate_lock(value)


def test_distinct_environments_have_no_shared_database_or_volume():
    module = environment_module()
    staging = module.environment_config('shop-001', 'staging', lock())
    live = module.environment_config('shop-001', 'live-test', lock())
    assert staging['compose_project'] != live['compose_project']
    assert staging['database_volume'] != live['database_volume']
    assert staging['site_volume'] != live['site_volume']
    assert staging['allow_real_payments'] is False
    assert staging['allow_email'] is False
    assert staging['allow_indexing'] is False
    assert live['allow_real_payments'] is False
    with pytest.raises(ValueError):
        module.environment_config('../other', 'staging', lock())
    with pytest.raises(ValueError):
        module.environment_config('shop-001', 'production', lock())
