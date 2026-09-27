import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from muse.contracts import ToolCall
from test_workspace_tools import context


async def test_real_browser_records_source_and_blocks_private_redirect(tmp_path, monkeypatch):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parents[3] / "work/browsers"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:9/private")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><title>Atlas</title><body><h1>Atlas</h1><p>Price: 120</p><script>window.privateValue='not content'</script></body></html>")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        repo, ctx, _ = context(tmp_path)
        origin = f"http://127.0.0.1:{server.server_port}"
        ctx.settings.browser_allowed_origins = [origin]
        from muse.tools.registry import ToolRegistry
        tools = ToolRegistry(ctx)
        result = await tools.execute(ToolCall(id="page", name="read_url", arguments={"url": origin + "/"}))
        assert result.status == "success", result.content
        assert "Price: 120" in result.content and "not content" not in result.content
        assert len(tools.artifacts.sources()) == 1
        blocked = await tools.execute(ToolCall(id="redirect", name="read_url", arguments={"url": origin + "/redirect"}))
        assert blocked.status in {"denied", "error"}
        assert len(tools.artifacts.sources()) == 1
    finally:
        server.shutdown()
        server.server_close()
