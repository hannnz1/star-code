"""Own one regex worker, with externally enforced deadlines and cleanup."""
import asyncio
import json
import os
import sys
import time

FILE_TIMEOUT = 0.250
SEARCH_TIMEOUT = 5.0


class RegexSession:
    def __init__(self, context, deadline):
        self.context = context
        self.deadline = deadline
        self.process = None

    async def start(self, pattern, case_sensitive):
        environment = {key: value for key, value in os.environ.items() if key.upper() in {
            'PATH', 'SYSTEMROOT', 'WINDIR', 'LANG', 'LC_ALL', 'TEMP', 'TMP',
        }}
        environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'muse.tools.regex_worker', cwd=self.context.settings.data_dir,
            env=environment, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=1024 * 1024)
        result = await self.exchange({'pattern': pattern, 'case_sensitive': case_sensitive}, SEARCH_TIMEOUT)
        if 'error' in result:
            raise ValueError('Invalid regex: ' + result['error'])
        if result != {'ready': True}:
            raise OSError('Regex worker did not initialize')

    async def exchange(self, payload, timeout):
        remaining = min(timeout, self.deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError('Regex search time limit exceeded')

        async def operation():
            self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + '\n').encode('utf-8'))
            await self.process.stdin.drain()
            response = await self.process.stdout.readline()
            if not response:
                raise OSError('Regex worker exited without a result')
            return json.loads(response)

        pending = asyncio.create_task(operation())
        try:
            return await self.context.controlled(asyncio.wait_for(pending, remaining))
        finally:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    async def matches(self, content, maximum):
        return (await self.exchange({'text': content, 'max_matches': maximum}, FILE_TIMEOUT))['matches']

    async def close(self):
        if self.process is not None:
            if self.process.returncode is None:
                self.process.kill()
            await asyncio.wait_for(self.process.wait(), timeout=2)
            if self.process.stdin is not None:
                self.process.stdin.close()
