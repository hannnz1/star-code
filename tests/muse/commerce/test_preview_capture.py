import hashlib
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from muse.commerce_connector.wordpress import WordPressConnection
from tests.muse.commerce.test_release_approval import product_review  # noqa: F401
from tests.muse.commerce.test_staging_verification import stage  # noqa: F401


@pytest.fixture
def preview_site(stage, monkeypatch):  # noqa: F811 - registered pytest fixture
    plan, code, snapshot = stage
    page_titles = {str(p['id']): p['title'] for p in snapshot.pages}
    data = {'mode': 'normal', 'requests': []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_GET(self):
            data['requests'].append(self.path)
            if self.path == data.get('media_path'):
                self.send_response(404 if data['mode'] == 'broken_image' else 200)
                self.send_header('Content-Type', 'image/png'); self.end_headers()
                self.wfile.write(data['media_bytes']); return
            if self.path.endswith('/cart'):
                self.send_response(200); self.send_header('Nonce', 'fixture-nonce'); self.end_headers()
                self.wfile.write(b'{}'); return
            query = parse_qs(urlsplit(self.path).query)
            product = 'p' in query
            title = 'Cup' if product else page_titles.get(query.get('page_id', [''])[0], 'Home')
            body = '<main><h1>' + title + '</h1><p>Fixture storefront</p></main>'
            if product and data.get('media_path'):
                visibility = ' style="display:none"' if data['mode'] == 'hidden_image' else ''
                body = body.replace('</main>', '<img src="' + data['media_path'] + '" alt="Cup"' + visibility + '></main>')
            if data['mode'] == 'external': body += '<script src="http://external.invalid/leak.js"></script>'
            if data['mode'] == 'broken_link': body += '<a href="/missing">Missing policy</a>'
            if data['mode'] == 'overflow': body = '<div style="width:2000px">' + body + '</div>'
            status = 404 if (data['mode'] == 'missing' and product) or self.path == '/missing' else 200
            self.send_response(status); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(('<!doctype html><html><head><style>body{margin:0}main{max-width:100%;padding:20px;box-sizing:border-box}</style></head><body>' + body + '</body></html>').encode())
        def do_POST(self):
            data['requests'].append(self.path)
            size = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(size))
            assert body == {'id': 201, 'quantity': 1}
            self.send_response(201); self.send_header('Nonce', 'fixture-nonce'); self.end_headers()
            self.wfile.write(b'{}')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    connection = WordPressConnection('stage', plan.project_id, 'staging', f'http://127.0.0.1:{server.server_port}',
                                     'scope-only', 'not-used', approved_development_http=True)
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'work/browsers')))
    yield plan, code, snapshot, connection, data
    server.shutdown(); server.server_close(); thread.join(5)


async def test_preview_captures_seven_routes_at_desktop_and_mobile_without_claiming_os_or_purchase(preview_site):
    from muse.commerce.preview import capture_staging_preview
    plan, code, snapshot, connection, data = preview_site
    result = await capture_staging_preview(plan, code, snapshot, connection)
    assert result.passed is True and result.site_verified is False
    assert set(result.checks) == {'pages', 'layout_desktop', 'layout_tablet', 'layout_mobile', 'links'}
    assert all(result.checks.values())
    assert len(result.frames) == 21 and {frame.width for frame in result.frames} == {390, 768, 1440}
    assert result.source_digest == code.source_digest
    for frame in result.frames:
        assert hashlib.sha256(frame.content).hexdigest() == frame.sha256
        with Image.open(io.BytesIO(frame.content)) as image:
            assert image.format == 'PNG' and image.width == frame.width
    assert not any('checkout' in url for url in data['requests'])  # No order or payment POST.


@pytest.mark.parametrize('mode,check', [('external', 'links'), ('overflow', 'layout_mobile'), ('missing', 'pages'), ('broken_link', 'links')])
async def test_preview_blocks_external_requests_and_reports_actual_layout_or_route_failures(preview_site, mode, check):
    from muse.commerce.preview import capture_staging_preview
    plan, code, snapshot, connection, data = preview_site
    data['mode'] = mode
    result = await capture_staging_preview(plan, code, snapshot, connection)
    assert result.passed is False and result.site_verified is False
    assert result.checks[check] is False


async def test_stale_facts_or_live_target_refused_before_any_browser_request(preview_site):
    from muse.commerce.errors import CommerceFailure
    from muse.commerce.preview import capture_staging_preview
    plan, code, snapshot, _connection, data = preview_site
    live = WordPressConnection('live', plan.project_id, 'live', 'https://live.example', 'scope', 'not-used')
    with pytest.raises(CommerceFailure):
        await capture_staging_preview(plan, code, snapshot, live)
    assert data['requests'] == []
