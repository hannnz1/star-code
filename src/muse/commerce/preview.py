"""Actual staging browser captures. No publication, OS or purchase approval.

The anonymous browser receives no connector credentials, paths or agent tools.
Only a preconfigured staging origin may load resources; redirects cannot expand
that origin. Screenshots and bounded diagnostics are returned to a trusted caller.
"""
import asyncio
import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import httpx
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright

from muse.commerce.errors import CommerceFailure
from muse.commerce.repository import digest
from muse.commerce.verification import verify_staging_facts
from muse.commerce_connector.wordpress import WordPressConnection

MAX_FRAME_BYTES = 5 * 1024 * 1024
MAX_CAPTURE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class PreviewFrame:
    kind: str
    width: int
    height: int
    sha256: str
    content: bytes
    sku: str | None = None


@dataclass(frozen=True)
class StagePreviewCapture:
    source_digest: str
    snapshot_hash: str
    connection_id: str
    target_url: str
    frames: tuple[PreviewFrame, ...]
    checks: dict[str, bool]
    diagnostics: tuple[str, ...]
    passed: bool
    site_verified: bool = False


def _inside(url, base):
    parsed, origin = urlsplit(url), urlsplit(base)
    return (parsed.scheme in {'http', 'https'} and (parsed.scheme, parsed.netloc) == (origin.scheme, origin.netloc)
            and parsed.username is None and parsed.password is None
            and parsed.path.startswith(origin.path.rstrip('/') + '/'))


async def _cart(context, base_url, product_id):
    # Populate this disposable anonymous cart, without an order/payment request.
    response = await context.request.get(base_url + '/wp-json/wc/store/v1/cart', max_redirects=0, timeout=10000)
    nonce = response.headers.get('nonce', '')
    if response.status != 200 or not 1 <= len(nonce) <= 100 or len(await response.body()) > 65536:
        return False
    response = await context.request.post(base_url + '/wp-json/wc/store/v1/cart/add-item',
        max_redirects=0, timeout=10000, headers={'Nonce': nonce}, data={'id': product_id, 'quantity': 1})
    return response.status == 201 and len(await response.body()) <= 65536


async def _check_link(client, url, base):
    # Only ordinary storefront navigation is probed. Cart actions and admin/API
    # links must never become commands as a side effect of inspecting a page.
    for _ in range(4):
        if not _inside(url, base):
            return False
        parsed = urlsplit(url)
        if any(part in parsed.path.split('/') for part in ('wp-admin', 'wp-json', 'wp-login.php')):
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        if set(query) - {'page_id', 'p', 'post_type', 's', 'paged', 'product_cat', 'orderby'}:
            return False
        try:
            async with client.stream('GET', url) as response:
                if response.status_code == 200:
                    return True
                if response.status_code not in (301, 302, 303, 307, 308):
                    return False
                location = response.headers.get('location')
                if not location:
                    return False
                url = urljoin(url, location)
        except httpx.HTTPError:
            return False
    return False


async def _product_images(page, project_id, refs, images, base_url):
    if not refs:
        return True
    files = {image.media_ref: image.image.sha256 + '.' +
        {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[image.image.mime_type] for image in images}
    expected = {base_url + '/wp-content/uploads/muse-owned/' + project_id + '/' + files[ref] for ref in refs}
    actual = await page.locator('main img').evaluate_all('''(items) => items.map(image => {
        const box = image.getBoundingClientRect(); const style = getComputedStyle(image);
        return {url: image.currentSrc || image.src,
            loaded: image.complete && image.naturalWidth > 0 && image.naturalHeight > 0,
            visible: box.width > 0 && box.height > 0 && style.display !== 'none' &&
                style.visibility !== 'hidden' && style.opacity !== '0'};
    })''')
    if not all(any(item['url'] == url and item['loaded'] and item['visible'] for item in actual) for url in expected):
        return False
    # Chromium can decode a valid PNG body even when its HTTP status is 404.
    # Independently require a successful bounded same-origin response, with
    # exact cleaned bytes, before treating that rendered image as evidence.
    descriptors = {base_url + '/wp-content/uploads/muse-owned/' + project_id + '/' + files[image.media_ref]:
        image.image.model_dump() for image in images if image.media_ref in refs}
    return await page.evaluate('''async (images) => {
        for (const [url, image] of Object.entries(images)) {
            try {
                const response = await fetch(url, {redirect: 'error', credentials: 'omit', cache: 'no-store',
                    signal: AbortSignal.timeout(10000)});
                if (!response.ok || response.url !== url || !response.body ||
                    response.headers.get('content-type')?.split(';')[0].trim() !== image.mime_type) return false;
                const reader = response.body.getReader(), chunks = []; let length = 0;
                while (true) {
                    const {value, done} = await reader.read(); if (done) break;
                    length += value.length;
                    if (length > image.byte_size || length > 10485760) {await reader.cancel(); return false;}
                    chunks.push(value);
                }
                if (length !== image.byte_size) return false;
                const bytes = new Uint8Array(length); let offset = 0;
                for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.length;}
                const digest = await crypto.subtle.digest('SHA-256', bytes);
                const sha = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
                if (sha !== image.sha256) return false;
            } catch (_) {return false;}
        }
        return true;
    }''', descriptors)


async def capture_staging_preview(plan, code, snapshot, connection, *, timeout=300, images=None, media_proofs=None, fixture=None):
    if (not isinstance(connection, WordPressConnection) or connection.environment != 'staging'
            or connection.project_id != plan.project_id or type(timeout) not in (int, float) or not 1 <= timeout <= 300):
        raise CommerceFailure('PERMISSION_DENIED', 403)
    facts = verify_staging_facts(plan, code, snapshot, connection=connection, images=images, media_proofs=media_proofs)
    probe = None
    if fixture is not None:
        from muse.commerce.buyer_fixture import DisposableBuyerProduct
        from muse.commerce.release_steps import _approved_product_facts
        if (type(fixture) is not DisposableBuyerProduct or fixture.project_id != plan.project_id
                or fixture.connection_id != connection.connection_id or fixture.draft.currency != snapshot.settings.get('currency')
                or any(product.stock >= 1 for product in plan.products)):
            raise CommerceFailure('REVIEW_STALE')
        matches = [product for product in snapshot.products if product.get('id') == fixture.product_id
            and product.get('sku') == fixture.draft.sku]
        if len(matches) != 1 or matches[0].get('status') != 'publish':
            raise CommerceFailure('REVIEW_STALE')
        _approved_product_facts(fixture.draft, matches[0])
        probe = fixture.draft
        facts['product_ids'][probe.sku] = fixture.product_id
    if not plan.products and probe is None:
        raise CommerceFailure('FACTS_INCOMPLETE', 422)
    def page_url(page):
        if snapshot.settings.get('permalink_structure'):
            return connection.base_url + ('/' if page.kind == 'home' else '/' + page.slug + '/')
        return connection.base_url + '/?page_id=' + str(facts['page_ids'][page.kind])
    routes = [(page.kind, page_url(page), page.title, None) for page in plan.blueprint.pages if page.kind != 'product']
    routes.extend(('product', connection.base_url + '/?post_type=product&p=' + str(facts['product_ids'][p.sku]), p.title, p.sku)
                  for p in plan.products)
    if probe is not None:
        routes.append(('product', connection.base_url + '/?post_type=product&p=' + str(fixture.product_id), probe.title, probe.sku))
    available = next((p for p in plan.products if p.stock > 0), probe)
    frames, diagnostics = [], []
    checks = dict.fromkeys(['pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links'], True)
    total_bytes = 0
    try:
        async with asyncio.timeout(timeout), async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-proxy-server'])
            try:
                for width in (1440, 768, 390):
                    context = await browser.new_context(viewport={'width': width, 'height': 900},
                        accept_downloads=False, service_workers='block')
                    try:
                        async def limit_origin(route):
                            if not _inside(route.request.url, connection.base_url):
                                checks['links'] = False
                                if 'EXTERNAL_RESOURCE_BLOCKED' not in diagnostics:
                                    diagnostics.append('EXTERNAL_RESOURCE_BLOCKED')
                                await route.abort()
                            else:
                                await route.continue_()
                        await context.route('**/*', limit_origin)
                        if available is None or not await _cart(context, connection.base_url, facts['product_ids'][available.sku]):
                            checks['pages'] = False
                            if 'CART_PREVIEW_UNAVAILABLE' not in diagnostics:
                                diagnostics.append('CART_PREVIEW_UNAVAILABLE')
                        page = await context.new_page()
                        checked_links = set()
                        for kind, url, title, sku in routes:
                            try:
                                response = await page.goto(url, wait_until='networkidle', timeout=15000)
                                if response is None or response.status != 200 or not _inside(page.url, connection.base_url):
                                    raise ValueError('Unverified route')
                                await page.locator('main').first.wait_for(state='visible', timeout=5000)
                                design = plan.blueprint.required_settings.get('store_design') if kind == 'home' else None
                                if design is None:
                                    await page.get_by_role('heading', name=title, exact=True).first.wait_for(state='visible', timeout=5000)
                                else:
                                    from muse.commerce.design_models import StoreDesignDocument
                                    from muse.commerce.design_resources import design_media_refs
                                    document = StoreDesignDocument.model_validate(design)
                                    sections = [section for section in document.home_sections if section.enabled]
                                    for section in sections:
                                        if section.props.title:
                                            await page.get_by_role('heading', name=section.props.title, exact=True).first.wait_for(state='visible', timeout=5000)
                                        for content in [section.props.text, *section.props.items]:
                                            if content:
                                                await page.locator('main').get_by_text(content, exact=True).first.wait_for(state='visible', timeout=5000)
                                    if not await _product_images(page, plan.project_id, design_media_refs(plan.blueprint), images or [], connection.base_url):
                                        raise ValueError('Design image differs from frozen bytes')
                                    font = await page.locator('body').evaluate('(element) => getComputedStyle(element).fontFamily')
                                    expected_font = 'Georgia' if document.theme_tokens.font == 'serif' else 'Arial'
                                    if expected_font not in font:
                                        raise ValueError('Design font differs from saved preset')
                                if kind == 'product':
                                    product = probe if probe is not None and probe.sku == sku else next(product for product in plan.products if product.sku == sku)
                                    if not await _product_images(page, plan.project_id, product.media_refs, images or [], connection.base_url):
                                        checks['pages'] = False
                                        diagnostics.append('PRODUCT_IMAGE_FAILED:' + sku + ':' + str(width))
                                inside = await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                                if not inside:
                                    checks[{1440: 'layout_desktop', 768: 'layout_tablet', 390: 'layout_mobile'}[width]] = False
                                    diagnostics.append('HORIZONTAL_OVERFLOW:' + kind + ':' + str(width))
                                links = await page.locator('a[href]').evaluate_all('(items) => items.map(item => item.href)')
                                if len(links) > 200 or any(not _inside(link, connection.base_url) for link in links if link):
                                    checks['links'] = False
                                cookies = {c['name']: c['value'] for c in await context.cookies(connection.base_url)}
                                async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False,
                                                             cookies=cookies) as client:
                                    for link in links[:200]:
                                        parsed = urlsplit(link)
                                        link = urlunsplit(parsed._replace(fragment=''))
                                        if link in checked_links:
                                            continue
                                        checked_links.add(link)
                                        if len(checked_links) > 200 or not await _check_link(client, link, connection.base_url):
                                            checks['links'] = False
                                            if 'STOREFRONT_LINK_FAILED' not in diagnostics:
                                                diagnostics.append('STOREFRONT_LINK_FAILED')
                                content = await page.screenshot(type='png', full_page=False, timeout=10000)
                                total_bytes += len(content)
                                if len(content) > MAX_FRAME_BYTES or total_bytes > MAX_CAPTURE_BYTES:
                                    raise ValueError('Capture exceeds limit')
                                frames.append(PreviewFrame(kind, width, 900, hashlib.sha256(content).hexdigest(), content, sku))
                            except (BrowserError, ValueError):
                                checks['pages'] = False
                                diagnostics.append('PAGE_CAPTURE_FAILED:' + kind + ':' + str(width))
                    finally:
                        await context.close()
            finally:
                await browser.close()
    except TimeoutError:
        checks = dict.fromkeys(checks, False)
        diagnostics.append('CAPTURE_TIMEOUT')
    except (BrowserError, OSError, ValueError):
        checks = dict.fromkeys(checks, False)
        diagnostics.append('BROWSER_UNAVAILABLE')
    passed = all(checks.values()) and len(frames) == len(routes) * 3
    return StagePreviewCapture(code.source_digest, digest(snapshot), connection.connection_id, connection.base_url,
                               tuple(frames), checks, tuple(diagnostics), passed)
