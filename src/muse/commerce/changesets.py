"""Deterministic review candidates. This factory cannot approve or publish.

Only the owned theme package is currently supported. Page ownership, navigation
and SKU absence require remote evidence unavailable in the current snapshot.
"""
import base64

from muse.commerce.coding import CodingArtifact, verify_coding_artifact
from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import (
    ChangeOperation,
    ChangeSet,
    CommercePlan,
    SitePackage,
    StoreSnapshot,
)
from muse.commerce.repository import digest
from muse.commerce.theme import build_site_archive
from muse.commerce_connector.operations import validate_operation


def create_changeset(plan: CommercePlan, snapshot: StoreSnapshot, package: SitePackage | None,
                     *, coding_artifact: CodingArtifact | None = None) -> ChangeSet:
    """Regenerate and compare the exact reviewed theme bytes from frozen inputs.

    Repeating the same revision produces the same IDs; a new review revision
    produces new operation IDs so an old receipt cannot stand in for a new write.
    The returned candidate still needs a trusted verifier and merchant approval.
    """
    if (not isinstance(plan, CommercePlan) or not isinstance(snapshot, StoreSnapshot)
            or (package is not None and not isinstance(package, SitePackage))):
        raise CommerceFailure('INPUT_INVALID', 422)
    try:
        plan = CommercePlan.model_validate(plan.model_dump(mode='json'))
        snapshot = StoreSnapshot.model_validate(snapshot.model_dump(mode='json'))
        package = None if package is None else SitePackage.model_validate(package.model_dump(mode='json'))
        # Free-form contract dictionaries may contain values that the field
        # validators accept but JSON serialization or UTF-8 hashing cannot.
        digest(plan)
        snapshot_hash = digest(snapshot)
        if package is not None:
            digest(package)
    except (ValueError, TypeError):
        raise CommerceFailure('INPUT_INVALID', 422) from None
    if plan.state not in {'VERIFYING', 'REVIEW_REQUIRED'}:
        raise CommerceFailure('REVIEW_STALE')
    if plan.project_id != snapshot.project_id or plan.snapshot_hash != snapshot_hash:
        raise CommerceFailure('REVIEW_STALE')
    if plan.kind != 'build_site':
        # A bounded product list cannot prove a SKU is absent on the platform.
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
    if package is None or plan.blueprint is None or plan.code_revision is None:
        raise CommerceFailure('FACTS_INCOMPLETE', 422)
    normalized = normalize_snapshot(snapshot.model_dump(mode='json'), snapshot.project_id, snapshot.environment)
    if normalized != snapshot:
        # Recompute fingerprints instead of trusting caller-provided digest maps.
        raise CommerceFailure('REVIEW_STALE')
    if snapshot.theme_identity.get('stylesheet') != 'muse-storefront':
        raise CommerceFailure('UNSUPPORTED_CAPABILITY', 422)
    try:
        if coding_artifact is None:
            generated, archive = build_site_archive(plan.blueprint, plan.products, code_revision=plan.code_revision)
        else:
            captured = verify_coding_artifact(coding_artifact)
            if (captured.project_id != plan.project_id or captured.plan_id != plan.id
                    or captured.snapshot_hash != plan.snapshot_hash
                    or captured.package.code_revision != plan.code_revision
                    or captured.package.content_sha256 != digest({'blueprint': plan.blueprint.model_dump(mode='json'),
                        'products': [p.model_dump(mode='json') for p in plan.products]})):
                raise CommerceFailure('REVIEW_STALE')
            generated, archive = captured.package, captured.archive
    except (ValueError, TypeError):
        raise CommerceFailure('VERIFICATION_FAILED', 422) from None
    if generated != package or plan.content_hash != generated.content_sha256:
        raise CommerceFailure('REVIEW_STALE')
    identity = digest({'plan_id': plan.id, 'project_id': plan.project_id, 'revision': plan.revision,
                       'snapshot': plan.snapshot_hash, 'package': generated.model_dump(mode='json')})
    theme_fingerprint = normalized.resource_fingerprints['theme']
    operation = validate_operation(ChangeOperation(
        operation_id='theme-' + identity, kind='install_theme_package', resource_key='theme:muse-storefront',
        expected_fingerprint=theme_fingerprint,
        payload={'package': generated.model_dump(mode='json'), 'archive_base64': base64.b64encode(archive).decode('ascii')},
    ))
    candidate = ChangeSet(id=identity, plan_id=plan.id, project_id=plan.project_id, environment=snapshot.environment,
                          operations=[operation], content_hash=generated.content_sha256,
                          package_hash=generated.package_sha256, digest='', resource_preconditions={
                              'theme:muse-storefront': theme_fingerprint,
                              'settings': normalized.resource_fingerprints['settings'],
                          })
    candidate.digest = digest(candidate.model_dump(mode='json', exclude={'digest'}))
    return candidate
