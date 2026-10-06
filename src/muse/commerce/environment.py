"""Fail-closed preflight for independently deployed reference stores."""
import re


def validate_lock(value: dict) -> dict:
    if value.get('verified') is not True:
        raise ValueError('Environment images have not been verified')
    images = value.get('images', {})
    for name in ('wordpress', 'database', 'cli'):
        image = images.get(name, '')
        if not isinstance(image, str) or not re.fullmatch(r'[a-zA-Z0-9._/:\-]+@sha256:[a-f0-9]{64}', image):
            raise ValueError('Environment image requires a resolved digest')
    for name in ('wordpress', 'woocommerce'):
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', str(value.get(name, ''))):
            raise ValueError('Environment versions must be explicit')
    return value


def environment_config(project_id: str, environment: str, lock: dict) -> dict:
    validate_lock(lock)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', project_id) or environment not in {'staging', 'live-test'}:
        raise ValueError('Invalid reference environment identity')
    prefix = f'muse-{project_id}-{environment}'
    return {'compose_project': prefix, 'database_volume': prefix + '-database',
            'site_volume': prefix + '-site', 'images': lock['images'],
            'allow_real_payments': False, 'allow_email': False, 'allow_indexing': False}
