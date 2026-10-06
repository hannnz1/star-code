import pytest

from muse.commerce.errors import CommerceFailure
from muse.commerce.release import release_source_hash
from tests.muse.commerce.test_merchant_release import merchant_inputs  # noqa: F401
from tests.muse.commerce.test_remote_media import image_upload  # noqa: F401
from tests.muse.commerce.test_site_release_intent import (
    site_release_inputs,  # noqa: F401
)


def test_launch_preview_builds_all_pages_without_changing_merchant_launch_source(merchant_inputs):  # noqa: F811
    from muse.commerce.staging_source import prepare_staging_source
    args = merchant_inputs
    args[1].kind = 'launch_products'
    source_hash = release_source_hash(args[1]); code = args[4]
    intent = prepare_staging_source(*args)
    assert intent.workflow == 'build_site' and len(intent.steps) == 18
    assert intent.plan_source_hash == source_hash and args[1].kind == 'launch_products'
    assert intent.code_revision == code.package.code_revision and intent.package == code.package
    assert sum(step.kind == 'create_owned_page' for step in intent.steps) == 6


def test_preview_declaration_never_targets_live(merchant_inputs):  # noqa: F811
    from muse.commerce.staging_source import prepare_staging_source
    args = list(merchant_inputs)
    args[2] = args[2].model_copy(update={'environment': 'live'})
    with pytest.raises(CommerceFailure): prepare_staging_source(*args)
