"""Read-only recovery of one recorded test store; no bootstrap retry or secrets output."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from muse.commerce.reference_environment import load_reference_assets
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.reference_runner import DockerReferenceRunner
from muse.commerce.repository import CommerceRepository
from muse.tasks.repository import TaskRepository


class DiagnosticRunner(DockerReferenceRunner):
    async def _read_safety(self, connection):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10,
                auth=(connection.username, connection.application_password)) as client:
            response = await client.get(connection.base_url + '/wp-json/muse-staging/v1/safety')
            redirect = urlsplit(response.headers.get('location', ''))
            print(json.dumps({'safety_status': response.status_code,
                              'content_type': response.headers.get('content-type', ''),
                              'redirect_host': redirect.hostname, 'redirect_port': redirect.port,
                              'redirect_path': redirect.path}))
        return await super()._read_safety(connection)


async def main(args):
    evidence = json.loads((args.root / 'evidence.json').read_text())
    identity = evidence['runtime_copies'][0]['job_id']
    lock = json.loads(args.lock.read_text())
    repo = CommerceRepository(TaskRepository(args.root / 'state.sqlite3'))
    jobs = ReferenceJobRepository(repo)
    rows = repo.db.rows("SELECT project_id FROM commerce_artifacts WHERE id=:id AND kind='reference_job'", {'id': identity})
    if len(rows) != 1:
        raise ValueError('Recorded reference identity differs')
    job = jobs.read(rows[0]['project_id'], identity)
    runner = DiagnosticRunner(jobs, args.root / 'private-0', lock)
    bundle = load_reference_assets(lock, args.woocommerce)
    errors = []
    def trace(frame, event, arg):
        if event == 'exception' and frame.f_code.co_filename.endswith(('reference_runner.py', 'reference_environment.py')):
            kind = arg[0].__name__
            if kind not in {'StopIteration', 'StopAsyncIteration', 'GeneratorExit'}:
                errors.append({'file': Path(frame.f_code.co_filename).name, 'line': frame.f_lineno,
                               'function': frame.f_code.co_name, 'type': kind})
        return trace
    try:
        sys.settrace(trace)
        result = await runner.verify(job, bundle)
        print(json.dumps({'verified': result['site_ready'], 'safety': result['safety']}))
    except Exception as error:  # noqa: BLE001 -- diagnostic boundary prints types only, never exception values
        print(json.dumps({'verified': False, 'type': type(error).__name__, 'exceptions': errors[-12:]}))
    finally:
        sys.settrace(None)
        for proxy in runner.preview_proxies.values():
            await proxy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--woocommerce', type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
