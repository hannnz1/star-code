"""Frozen workflow input and the selected provider identity, without plaintext secrets."""
import hashlib

from muse.commerce.repository import digest


def provider_identity(settings):
    if settings.provider is None:
        return None
    return digest({'settings': settings.provider.model_dump(mode='json'),
                   'credential_digest': hashlib.sha256(settings.provider.api_key.get_secret_value().encode()).hexdigest()})
