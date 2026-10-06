"""Deterministic structure draft; never implies a staged or verified website."""
from muse.commerce.models import (
    BlueprintPage,
    NavigationItem,
    SiteBlueprint,
    SiteBrief,
    StoreSnapshot,
)


def build_site_blueprint(brief: SiteBrief, snapshot: StoreSnapshot) -> SiteBlueprint:
    labels = ['首页', '商店', '商品详情', '购物车', '结账', '关于我们', '联系我们'] if brief.language.lower().startswith('zh') else [
        'Home', 'Shop', 'Product', 'Cart', 'Checkout', 'About', 'Contact']
    kinds = ['home', 'shop', 'product', 'cart', 'checkout', 'about', 'contact']
    pages = [BlueprintPage(kind=kind, slug=kind, title=label) for kind, label in zip(kinds, labels, strict=True)]
    missing = ['merchant_supplied_policies.' + name for name in ('shipping', 'returns', 'privacy')
               if not brief.merchant_supplied_policies.get(name, '').strip()]
    for field in ('shipping_confirmed', 'payment_confirmed'):
        if snapshot.settings.get(field) is not True:
            missing.append(field)
    if snapshot.settings.get('currency') != brief.currency:
        missing.append('store_currency')
    if snapshot.theme_identity.get('stylesheet') != 'muse-storefront':
        missing.append('owned_block_theme')
    return SiteBlueprint(pages=pages,
        navigation=[NavigationItem(slug=page.slug, label=page.title) for page in pages if page.kind not in {'product', 'checkout'}],
        design_tokens={'background': '#f8faf4', 'text': '#34553d', 'accent': '#5f8152'},
        required_settings={'language': brief.language, 'currency': brief.currency, 'missing_fields': missing,
            'commerce_blocks': {'cart': 'woocommerce/cart', 'checkout': 'woocommerce/checkout'},
            'buyer_flow_verified': False})
