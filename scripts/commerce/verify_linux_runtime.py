"""Actual Linux/Docker acceptance; requires preloaded, digest-pinned images.

The test-only candidate lock does not modify the deployable version lock. No
production database or credentials are copied. Evidence never contains secrets.
"""
import argparse
import asyncio
import hashlib
import json
import platform
from pathlib import Path

from muse.commerce.errors import CommerceFailure
from muse.commerce.isolation import DockerCodingSession
from muse.commerce.models import SiteBrief
from muse.commerce.reference_environment import load_reference_assets
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.reference_runner import DockerReferenceRunner
from muse.commerce.repository import CommerceRepository
from muse.commerce.theme import seed_files
from muse.tasks.repository import TaskRepository


class DiagnosticRunner(DockerReferenceRunner):
    failure = None

    async def _cli(self, *args, **kwargs):
        try:
            return await super()._cli(*args, **kwargs)
        except BaseException as error:
            self.failure = {'command': list(args[:3]), 'exception_type': type(error).__name__}
            raise


async def verify(args):
    if args.cleanup_only:
        if platform.system() != 'Linux':
            raise ValueError('Linux required')
        evidence = json.loads((args.root / 'evidence.json').read_text())
        lock = json.loads(args.lock.read_text())
        jobs = ReferenceJobRepository(CommerceRepository(TaskRepository(args.root / 'state.sqlite3')))
        for index, item in enumerate(evidence['runtime_copies']):
            rows = jobs.db.rows("SELECT project_id FROM commerce_artifacts WHERE id=:id AND kind='reference_job'",
                                {'id': item['job_id']})
            if len(rows) != 1:
                raise ValueError('Test job identity differs')
            job = jobs.read(rows[0]['project_id'], item['job_id'])
            runner = DockerReferenceRunner(jobs, args.root / f'private-{index}', lock)
            cleaned = await runner.cleanup(job)
            item['cleanup_state'] = cleaned.state
            (args.root / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        return
    if platform.system() != 'Linux' or args.root.exists():
        raise ValueError('A new private Linux test directory is required')
    args.root.mkdir(mode=0o700, parents=True)
    lock = json.loads(args.lock.read_text())
    evidence = {'kernel': platform.release(), 'images': lock['images'], 'production_verified': False,
                'isolation': None, 'runtime_copies': []}
    def save():
        (args.root / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    session = DockerCodingSession(args.root / 'coding', lock)
    try:
        evidence['isolation'] = await session.start(seed_files())
        evidence['isolation']['write_read_pass'] = (await session.run('printf muse-probe > /workspace/probe; cat /workspace/probe; rm /workspace/probe')) == 'muse-probe'
        capture = await session.capture()
        evidence['isolation']['capture_sha256'] = hashlib.sha256(capture).hexdigest()
        save()
    finally:
        await session.close()
    repo = CommerceRepository(TaskRepository(args.root / 'state.sqlite3'))
    jobs = ReferenceJobRepository(repo)
    bundle = load_reference_assets(lock, args.woocommerce)
    identities = []
    for index in range(2):
        space = args.root / f'workspace-{index}'
        space.mkdir()
        project = repo.create_project(repo.runtime.register_workspace(str(space))['id'],
            SiteBrief(brand_name=f'Acceptance Store {index}', language='en-US', currency='USD'), f'linux-{index}')
        job = jobs.reserve(project.id, project.revision, 'runtime', bundle.source_digest, args.port + index)
        runner = DiagnosticRunner(jobs, args.root / f'private-{index}', lock)
        item = {'job_id': job.id, 'resource_names': job.resource_names, 'state': job.state}
        evidence['runtime_copies'].append(item)
        save()
        try:
            await runner.prepare(job, bundle)
            current = jobs.read(project.id, job.id)
            item['state'] = current.state
            save()
            ready = await runner.bootstrap(current, bundle, currency='USD', language='en-US')
            item.update(state='READY', safety=ready['safety'], assets_verified=ready['assets_verified'])
            if args.publish_probe:
                from linux_release_probe import release_probe
                item['release_probe'] = await release_probe(runner, jobs.read(project.id, job.id), bundle,
                                                            args.root / f'operations-{index}.sqlite3')
            identities.append(set(job.resource_names.values()))
            save()
        except Exception:
            item['state'] = jobs.read(project.id, job.id).state
            item['failure'] = runner.failure
            diagnostics = []
            for role in ('database', 'wordpress', 'cli'):
                try:
                    raw = await runner._cli('inspect', job.resource_names[role], limit=131072)
                    records = json.loads(raw)
                    for record in records:
                        diagnostics.append({'role': role, 'inspect_bytes': len(raw), 'running': record['State']['Running'],
                            'exit_code': record['State']['ExitCode'], 'image': record['Image'],
                            'user': record['Config']['User'], 'cap_add': record['HostConfig']['CapAdd'],
                            'cap_drop': record['HostConfig']['CapDrop'], 'ports': record['NetworkSettings']['Ports'],
                            'config_image': record['Config']['Image'], 'labels': record['Config']['Labels'],
                            'mounts': record['Mounts'], 'networks': list(record['NetworkSettings']['Networks']),
                            'host': {key: record['HostConfig'].get(key) for key in ('ReadonlyRootfs', 'Privileged',
                                'SecurityOpt', 'NetworkMode', 'PortBindings', 'Memory', 'NanoCpus', 'PidsLimit',
                                'PidMode', 'IpcMode', 'UTSMode', 'UsernsMode', 'Devices', 'VolumesFrom', 'Links', 'ExtraHosts')}})
                except (CommerceFailure, ValueError, KeyError, TypeError, OSError, TimeoutError):
                    diagnostics.append({'role': role, 'inspect_available': False})
            item['diagnostics'] = diagnostics
            save()
            raise
        finally:
            current = jobs.read(project.id, job.id)
            if current.state != 'CLEANED' and not args.keep_resources:
                cleaned = await runner.cleanup(current)
                item['cleanup_state'] = cleaned.state
                save()
    evidence['separate_resources_pass'] = len(identities) == 2 and identities[0].isdisjoint(identities[1])
    save()
    print(json.dumps({'isolation_pass': bool(evidence['isolation']),
        'copies_ready': sum(item['state'] == 'READY' for item in evidence['runtime_copies']),
        'separate_resources_pass': evidence['separate_resources_pass']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--woocommerce', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18081)
    parser.add_argument('--cleanup-only', action='store_true', help='Inventory and clean only this recorded test run')
    parser.add_argument('--keep-resources', action='store_true', help='Retain only this test run for local diagnosis')
    parser.add_argument('--publish-probe', action='store_true', help='Publish synthetic products in disposable copies only')
    asyncio.run(verify(parser.parse_args()))
