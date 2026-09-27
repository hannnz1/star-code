import asyncio
import ipaddress
import json
import socket
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from muse.artifacts.service import ArtifactService


class URLPolicy:
    def __init__(self, allowed_origins=None, resolver=None):
        self.allowed_origins = set(allowed_origins or [])
        self.resolver = resolver

    async def check(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise PermissionError("Only public HTTP(S) URLs without credentials are allowed")
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin in self.allowed_origins:
                return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
            addresses = await self.resolver(parsed.hostname) if self.resolver else await asyncio.to_thread(
                lambda: list({entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}))
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise PermissionError("Private, loopback and special-use network addresses are blocked")
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
        except (ValueError, socket.gaierror):
            raise PermissionError("URL could not be resolved safely") from None

    async def connection_plan(self, url: str) -> dict:
        normalized = await self.check(url)
        parsed = urlsplit(normalized)
        hostname = parsed.hostname.encode("idna").decode("ascii")
        try:
            addresses = await self.resolver(hostname) if self.resolver else await asyncio.to_thread(
                lambda: list({entry[4][0] for entry in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}))
            if not addresses or (f"{parsed.scheme}://{parsed.netloc}" not in self.allowed_origins and any(not ipaddress.ip_address(address).is_global for address in addresses)):
                raise PermissionError("Destination changed to a non-public address")
            # Prefer usable IPv4 on dual-stack hosts; set iteration order must not pick IPv6 randomly.
            addresses.sort(key=lambda address: (ipaddress.ip_address(address).version, ipaddress.ip_address(address).packed))
            return {"url": normalized, "hostname": hostname, "address": addresses[0], "origin": f"{parsed.scheme}://{parsed.netloc}"}
        except (ValueError, socket.gaierror):
            raise PermissionError("Destination could not be pinned safely") from None


class BrowserTool:
    def __init__(self, context):
        self.ctx = context
        self.policy = URLPolicy(context.settings.browser_allowed_origins)
        self.artifacts = ArtifactService(context)

    @staticmethod
    def launch_options(plan):
        address = f"[{plan['address']}]" if ":" in plan["address"] else plan["address"]
        return {"headless": True, "args": [f"--host-resolver-rules=MAP {plan['hostname']} {address}", "--no-proxy-server", "--dns-prefetch-disable"]}

    async def read(self, args, call_id):
        plan = await self.policy.connection_plan(args["url"])
        url = plan["url"]
        blocked = []
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(**self.launch_options(plan))
            except PlaywrightError:
                raise ValueError("Browser could not start. Check process permissions and install Chromium with python -m playwright install chromium (or run Setup-MUSE.ps1).") from None
            try:
                context = await browser.new_context(accept_downloads=False, service_workers="block", java_script_enabled=False)

                async def route_request(route):
                    try:
                        await self.policy.check(route.request.url)
                        destination = urlsplit(route.request.url)
                        if f"{destination.scheme}://{destination.netloc}" != plan["origin"]:
                            raise PermissionError("Cross-origin navigation requires its own explicitly supplied URL")
                        if route.request.method != "GET" or route.request.resource_type != "document":
                            await route.abort()
                        else:
                            await route.continue_()
                    except PermissionError:
                        blocked.append(route.request.url)
                        await route.abort()

                await context.route("**/*", route_request)
                await context.route_web_socket("**/*", lambda route: route.close())
                page = await context.new_page()
                try:
                    response = await self.ctx.controlled(page.goto(url, wait_until="domcontentloaded", timeout=25000))
                    if response is None or response.status >= 400:
                        raise ValueError(f"Source unavailable (HTTP {response.status if response else 'unknown'})")
                    final_url = await self.policy.check(page.url)
                    markup = await page.content()
                    if len(markup) > 2 * 1024 * 1024:
                        raise ValueError("Web page exceeds the extraction limit")
                    soup = BeautifulSoup(markup, "html.parser")
                    title = soup.title.get_text(" ", strip=True) if soup.title else final_url
                    for unwanted in soup(["script", "style", "noscript", "svg"]):
                        unwanted.decompose()
                    content = soup.get_text("\n", strip=True)
                    source = self.artifacts.source(final_url, title, content[:200000])
                    ids = self.ctx.cp.setdefault("source_ids", [])
                    if source["id"] not in ids:
                        ids.append(source["id"])
                    return json.dumps({"source_id": source["id"], "url": final_url, "title": title,
                                       "text": self.ctx.safe(content[:60000]), "truncated": len(content) > 60000,
                                       "blocked_requests": len(blocked)}, ensure_ascii=False)
                except PlaywrightError:
                    raise ValueError("Browser could not read the source; navigation failed or was blocked") from None
            finally:
                await browser.close()
