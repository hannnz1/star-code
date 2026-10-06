"""v4 projection shares exact website effects, with frozen image creation first."""
from muse.commerce.merchant_release import validate_merchant_release
from muse.commerce.site_steps import _project


def project_merchant_step(intent, connection, code, index, history, snapshot, proofs):
    return _project(intent, connection, code, index, history, snapshot, proofs, validator=validate_merchant_release)


def validate_merchant_completion(intent, connection, code, history, snapshot, proofs):
    return _project(intent, connection, code, len(intent.steps), history, snapshot, proofs,
        complete=True, validator=validate_merchant_release)
