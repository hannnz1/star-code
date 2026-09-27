import importlib.util

import pytest


def url_policy(**kwargs):
    assert importlib.util.find_spec("muse.tools.browser") is not None, "Browser policy missing"
    from muse.tools.browser import URLPolicy
    return URLPolicy(**kwargs)


@pytest.mark.parametrize("url", ["file:///C:/private.txt", "http://127.0.0.1:1234/", "http://169.254.169.254/", "http://[::1]/", "https://user:pass@example.com/"])
async def test_unsafe_urls_are_blocked(url):
    with pytest.raises(PermissionError):
        await url_policy().check(url)


async def test_fixture_exception_matches_exact_origin_only():
    p = url_policy(allowed_origins=["http://127.0.0.1:32123"])
    assert await p.check("http://127.0.0.1:32123/index.html")
    with pytest.raises(PermissionError):
        await p.check("http://127.0.0.1:32124/index.html")


async def test_non_global_dns_answer_is_rejected_even_for_public_name():
    async def resolve(host):
        return ["93.184.216.34", "127.0.0.1"]
    with pytest.raises(PermissionError):
        await url_policy(resolver=resolve).check("https://example.com")

async def test_public_dual_stack_selection_prefers_ipv4_deterministically():
    from muse.tools.browser import URLPolicy
    async def resolver(host):return ['2a04:4e42::223','151.101.0.223']
    plan=await URLPolicy(resolver=resolver).connection_plan('https://docs.python.org/3.12/library/asyncio-task.html')
    assert plan['address']=='151.101.0.223'
