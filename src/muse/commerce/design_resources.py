"""Shared, ordered image scope for products and frozen structured design."""
def design_media_refs(blueprint):
    raw = blueprint.required_settings.get('store_design') if blueprint else None
    if not raw: return []
    from muse.commerce.design_models import StoreDesignDocument
    document = StoreDesignDocument.model_validate(raw)
    return list(dict.fromkeys(s.props.media_id for s in document.home_sections if s.enabled and s.props.media_id))


def source_media_refs(blueprint, products):
    return list(dict.fromkeys([ref for p in products for ref in p.media_refs] + design_media_refs(blueprint)))


def publication_images(workflow, blueprint, products, images):
    if workflow == 'launch_products' and blueprint.required_settings.get('retain_existing_theme'):
        refs = list(dict.fromkeys(ref for product in products for ref in product.media_refs))
        by_ref = {image.media_ref:image for image in images}
        return [by_ref[ref] for ref in refs]
    return images


def owned_image_path(project_id, sha, mime):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',project_id) or not re.fullmatch(r'[a-f0-9]{64}',sha):
        raise ValueError('Invalid owned image identity')
    extension={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime]
    return '/wp-content/uploads/muse-owned/'+project_id+'/'+sha+'.'+extension
