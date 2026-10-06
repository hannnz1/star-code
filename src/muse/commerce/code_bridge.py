"""Lease-bound static code editing. No host execution or WordPress permission.

Drafts and managed tool receipts commit together. Immutable source objects may
remain after a rolled-back seal; they cannot authorize or deploy anything.
"""
import base64
import difflib
import hashlib
import io
import json
import tarfile
import zipfile
from contextlib import nullcontext

from sqlalchemy import text

from muse.commerce.coding import CodingArtifact, SourceStore, verify_coding_artifact
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import SitePackage, ThemeCodeReview
from muse.commerce.orchestration import CommerceWorkflowService
from muse.commerce.repository import CommerceRepository, digest, encode
from muse.commerce.theme import (
    ALLOWED_FILES,
    MAX_FILE,
    render_site_files,
    validate_theme_files,
)


def theme_seed_files(conn, plan):
    reference = plan.blueprint.required_settings.get('restored_theme_source')
    if reference is None:
        return render_site_files(plan.blueprint, plan.products)
    from muse.commerce.restore import ProjectRestorer
    if (not isinstance(reference, dict) or set(reference) != {'id', 'digest'}
            or not all(isinstance(value, str) and value for value in reference.values())):
        raise CommerceFailure('RESOURCE_CONFLICT')
    source, _ = ProjectRestorer._theme_source(conn, plan.project_id, reference['id'], reference['digest'])
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(source.archive_base64, validate=True))) as archive:
        return {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}


class ThemeCodeBridge:
    def __init__(self, ctx):
        self.ctx = ctx
        self.service = CommerceWorkflowService(CommerceRepository(ctx.repo), ctx.settings)

    def _load(self, conn):
        plan, step, _ = self.service._actor(conn, self.ctx)
        if step.role != 'site_developer':
            raise CommerceFailure('PERMISSION_DENIED', 403)
        if (plan.state not in {'PLANNING', 'BUILDING'} or step.status == 'SUCCEEDED'
                or plan.blueprint is None or plan.snapshot_hash is None):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
        seed = theme_seed_files(conn, plan)
        binding = {'project_id': plan.project_id, 'plan_id': plan.id, 'step_id': step.id,
                   'task_id': self.ctx.task_id, 'snapshot_hash': plan.snapshot_hash, 'content_hash': plan.content_hash}
        identity = digest([plan.id, step.id, 'theme-code'])
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='theme_code_draft'"),
                           {'id': identity, 'project': plan.project_id, 'plan': plan.id}).mappings().first()
        if row:
            try:
                saved = json.loads(row['data'])
                if digest(saved) != row['digest'] or saved['binding'] != binding:
                    raise ValueError('Draft binding differs')
                files = {name: base64.b64decode(value, validate=True) for name, value in saved['files'].items()}
                validate_theme_files(files)
            except (ValueError, KeyError, TypeError):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id) from None
        else:
            files = seed
            saved = {'binding': binding, 'files': {}, 'sealed': None}
        return plan, identity, saved, files, seed

    @staticmethod
    def _hash(files):
        return digest({name: hashlib.sha256(content).hexdigest() for name, content in files.items()})

    def _save(self, conn, plan, identity, saved, files, call_id):
        saved['files'] = {name: base64.b64encode(value).decode('ascii') for name, value in files.items()}
        conn.execute(text("INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,'theme_code_draft',:digest,:data) ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,data=excluded.data"),
                     {'id': identity, 'project': plan.project_id, 'plan': plan.id, 'digest': digest(saved), 'data': encode(saved)})
        self.service._receipt(conn, self.ctx, call_id)

    def read(self, name):
        if name not in ALLOWED_FILES:
            raise CommerceFailure('INPUT_INVALID', 422)
        with self.ctx.repo.db.transaction() as conn:
            _, _, _, files, _ = self._load(conn)
            return {'path': name, 'content': files[name].decode('utf-8'), 'draft_hash': self._hash(files)}

    def write(self, name, content, expected_hash, *, call_id=None):
        if name not in ALLOWED_FILES or name == 'functions.php' or not isinstance(content, str):
            raise CommerceFailure('INPUT_INVALID', 422)
        try:
            raw = content.encode('utf-8')
            if len(raw) > MAX_FILE:
                raise ValueError('File too large')
        except (ValueError, UnicodeError):
            raise CommerceFailure('INPUT_INVALID', 422) from None
        with self.ctx.repo.db.transaction() as conn:
            plan, identity, saved, files, _ = self._load(conn)
            if saved['sealed'] or expected_hash != self._hash(files):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            files[name] = raw
            try:
                validate_theme_files(files)
            except (ValueError, TypeError):
                raise CommerceFailure('INPUT_INVALID', 422) from None
            self._save(conn, plan, identity, saved, files, call_id)
            self.service.repo.event(conn, plan.project_id, 'theme_code_edited', {'plan_id': plan.id, 'path': name, 'draft_hash': self._hash(files)})
            return {'path': name, 'draft_hash': self._hash(files), 'published': False}

    def diff(self):
        with self.ctx.repo.db.transaction() as conn:
            _, _, _, files, seed = self._load(conn)
            output = ''.join(''.join(difflib.unified_diff(seed[name].decode().splitlines(keepends=True),
                files[name].decode().splitlines(keepends=True), fromfile='before/' + name, tofile='after/' + name))
                for name in sorted(files) if files[name] != seed[name])
            # The normal tool offload mechanism preserves larger diffs.
            return {'diff': output, 'draft_hash': self._hash(files), 'published': False}

    def seal(self, expected_hash, *, call_id=None):
        with self.ctx.repo.db.transaction() as conn:
            plan, identity, saved, files, _ = self._load(conn)
            if expected_hash != self._hash(files):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id)
            if not saved['sealed']:
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode='w') as archive:
                    for name, content in sorted(files.items()):
                        entry = tarfile.TarInfo(name)
                        entry.size = len(content)
                        archive.addfile(entry, io.BytesIO(content))
                try:
                    artifact = SourceStore(self.ctx.settings.data_dir / 'commerce-source.git').seal(stream.getvalue(),
                        project_id=plan.project_id, plan_id=plan.id, snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
                except (ValueError, OSError):
                    raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503) from None
                saved['sealed'] = {'package': artifact.package.model_dump(mode='json'), 'source_digest': artifact.source_digest,
                                   'archive': base64.b64encode(artifact.archive).decode('ascii')}
                plan.code_revision, plan.state = artifact.package.code_revision, 'BUILDING'
                self.service._persist(conn, plan)
                self.service.repo.event(conn, plan.project_id, 'theme_code_sealed', {'plan_id': plan.id, 'code_revision': plan.code_revision,
                    'package_sha256': artifact.package.package_sha256, 'site_verified': False})
            self._save(conn, plan, identity, saved, files, call_id)
            package = saved['sealed']['package']
            return {'code_revision': package['code_revision'], 'package_sha256': package['package_sha256'],
                    'draft_hash': self._hash(files), 'site_verified': False, 'published': False}

    def captured(self):
        with self.ctx.repo.db.transaction() as conn:
            plan, _, saved, _, _ = self._load(conn)
            if not saved['sealed']:
                raise CommerceFailure('FACTS_INCOMPLETE', 422)
            try:
                value = saved['sealed']
                artifact = CodingArtifact(plan.project_id, plan.id, plan.snapshot_hash, value['source_digest'],
                    SitePackage.model_validate(value['package']), base64.b64decode(value['archive'], validate=True))
                verify_coding_artifact(artifact)
                if artifact.package.code_revision != plan.code_revision:
                    raise ValueError('Plan code differs')
                return artifact
            except (ValueError, KeyError, TypeError):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id) from None


def load_captured_code(repository, plan, *, connection=None):
    """Trusted verifier reader; no task lease, mutation, or approval is provided."""
    step = next((s for s in plan.steps if s.role == 'site_developer'), None)
    if step is None:
        raise CommerceFailure('FACTS_INCOMPLETE', 422)
    with nullcontext(connection) if connection is not None else repository.db.transaction() as conn:
        theme_seed_files(conn, plan)
        current = conn.execute(text('SELECT data FROM commerce_plans WHERE id=:id AND project_id=:project'),
            {'id': plan.id, 'project': plan.project_id}).scalar()
        if current != encode(plan):
            raise CommerceFailure('REVIEW_STALE')
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='theme_code_draft'"),
            {'id': digest([plan.id, step.id, 'theme-code']), 'project': plan.project_id, 'plan': plan.id}).mappings().first()
        if row is None:
            raise CommerceFailure('FACTS_INCOMPLETE', 422)
        try:
            saved = json.loads(row['data'])
            binding = {'project_id': plan.project_id, 'plan_id': plan.id, 'step_id': step.id,
                       'task_id': step.task_id, 'snapshot_hash': plan.snapshot_hash, 'content_hash': plan.content_hash}
            if digest(saved) != row['digest'] or saved['binding'] != binding:
                raise ValueError('Code binding differs')
            value = saved['sealed']
            artifact = CodingArtifact(plan.project_id, plan.id, plan.snapshot_hash, value['source_digest'],
                SitePackage.model_validate(value['package']), base64.b64decode(value['archive'], validate=True))
            verify_coding_artifact(artifact)
            files = {name: base64.b64decode(value, validate=True) for name, value in saved['files'].items()}
            validate_theme_files(files)
            if (artifact.package.code_revision != plan.code_revision or artifact.package.content_sha256 != plan.content_hash
                    or ThemeCodeBridge._hash(files) != artifact.source_digest):
                raise ValueError('Sealed code differs')
            return artifact
        except (ValueError, KeyError, TypeError):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=plan.project_id) from None


def review_captured_code(repository, plan):
    with repository.db.transaction() as conn:
        captured = load_captured_code(repository, plan, connection=conn)
        seed = theme_seed_files(conn, plan)
        with zipfile.ZipFile(io.BytesIO(captured.archive)) as archive:
            files = {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}
        diff = ''.join(''.join(difflib.unified_diff(seed[name].decode().splitlines(keepends=True),
            files[name].decode().splitlines(keepends=True), fromfile='before/' + name, tofile='after/' + name))
            for name in sorted(files) if files[name] != seed[name])
        return ThemeCodeReview(plan_id=plan.id, plan_revision=plan.revision, code_revision=captured.package.code_revision,
            package_sha256=captured.package.package_sha256, source_digest=captured.source_digest,
            files_manifest=captured.package.files_manifest, diff=diff)
