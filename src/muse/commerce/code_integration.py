"""Three-way file merge into a local static-theme baseline, never deployment.

Plans retain independent immutable sources. Non-overlapping line edits combine;
overlapping edits require a new task to resolve them explicitly.
"""
import base64
import difflib
import hashlib
import io
import json
import tarfile
import time
import zipfile

from sqlalchemy import text

from muse.commerce.code_bridge import load_captured_code, theme_seed_files
from muse.commerce.coding import SourceStore
from muse.commerce.errors import CommerceFailure
from muse.commerce.models import CodeDisposition, CodeIntegrationReview, CommerceCodeHead, CommercePlan
from muse.commerce.repository import digest, encode
from muse.commerce.restore import ProjectRestorer
from muse.commerce.theme import ALLOWED_FILES, validate_theme_files


def source_files(source):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(source.archive_base64, validate=True))) as archive:
        return {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}


def merge_lines(base, current, candidate):
    """Conservative three-way text merge; touching insertions remain conflicts."""
    original = base.decode('utf-8').splitlines(keepends=True)
    edits = []
    for content in (current, candidate):
        lines = content.decode('utf-8').splitlines(keepends=True)
        changes = [(start, end, lines[left:right]) for tag, start, end, left, right
                   in difflib.SequenceMatcher(None, original, lines, autojunk=False).get_opcodes()
                   if tag != 'equal']
        for change in changes:
            if change in edits:
                continue
            start, end, _ = change
            for other_start, other_end, _ in edits:
                overlap = max(start, other_start) < min(end, other_end)
                insertion_touches = (start == end and other_start <= start <= other_end
                                     or other_start == other_end and start <= other_start <= end)
                if overlap or insertion_touches:
                    return None
            edits.append(change)
    result, cursor = [], 0
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1])):
        result.extend(original[cursor:start])
        result.extend(replacement)
        cursor = end
    result.extend(original[cursor:])
    return ''.join(result).encode('utf-8')


def merge_files(base, current, candidate):
    merged, conflicts = {}, []
    for name in sorted(ALLOWED_FILES):
        if candidate[name] == base[name]:
            merged[name] = current[name]
        elif current[name] in (base[name], candidate[name]):
            merged[name] = candidate[name]
        else:
            combined = merge_lines(base[name], current[name], candidate[name])
            if combined is None:
                conflicts.append(name)
            else:
                merged[name] = combined
    if not conflicts:
        try:
            validate_theme_files(merged)
        except ValueError:
            raise CommerceFailure('VERIFICATION_FAILED') from None
    return merged, conflicts


def files_digest(files):
    return digest({name: hashlib.sha256(content).hexdigest() for name, content in files.items()})


class CommerceCodeIntegration:
    def __init__(self, repo, source_root):
        self.repo, self.source_root = repo, source_root

    def dispositions(self, project_id):
        self.repo.get_project(project_id)
        with self.repo.db.transaction() as conn:
            return [self._disposition(conn, project_id, row[0]) for row in conn.execute(text(
                "SELECT plan_id FROM commerce_artifacts WHERE project_id=:project AND kind='code_disposition'"), {'project': project_id})]

    @staticmethod
    def _disposition(conn, project_id, plan_id):
        raw = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND plan_id=:plan AND kind='code_disposition'"),
            {'id': digest([project_id, plan_id, 'code-disposition']), 'project': project_id, 'plan': plan_id}).mappings().first()
        if not raw:
            return None
        value = CodeDisposition.model_validate_json(raw['data'])
        if digest(value.model_dump(mode='json')) != raw['digest']:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return value

    @staticmethod
    def head(conn, project_id):
        identity = digest([project_id, 'local-code-head'])
        row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='local_code_head'"),
                           {'id': identity, 'project': project_id}).mappings().first()
        if not row:
            return None
        value = CommerceCodeHead.model_validate_json(row['data'])
        if digest(value.model_dump(mode='json')) != row['digest'] or value.project_id != project_id:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        source, _ = ProjectRestorer._theme_source(conn, project_id, value.source_id)
        if source.package.code_revision != value.code_revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        return value

    def _review(self, conn, project_id, plan_id, plan_revision):
        project = self.repo._project(conn, project_id)
        row = conn.execute(text('SELECT data,root_task_id FROM commerce_plans WHERE id=:id AND project_id=:project'),
                           {'id': plan_id, 'project': project_id}).mappings().first()
        if not row:
            raise CommerceFailure('NOT_FOUND', 404, project_id=project_id)
        plan = CommercePlan.model_validate_json(row['data'])
        if plan.revision != plan_revision:
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        root = conn.execute(text('SELECT checkpoint,status,cancel_requested FROM tasks WHERE id=:id'),
                            {'id': row['root_task_id']}).mappings().first()
        binding = json.loads(root['checkpoint']).get('commerce', {}) if root else {}
        if (binding.get('project_revision') != project.revision or binding.get('project_id') != project_id
                or binding.get('plan_id') != plan_id):
            raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
        captured = load_captured_code(self.repo, plan, connection=conn)
        with zipfile.ZipFile(io.BytesIO(captured.archive)) as archive:
            candidate = {name: archive.read('muse-storefront/' + name) for name in ALLOWED_FILES}
        base = theme_seed_files(conn, plan)
        head = self.head(conn, project_id)
        current = source_files(ProjectRestorer._theme_source(conn, project_id, head.source_id)[0]) if head else base
        merged, conflicts = merge_files(base, current, candidate)
        changed = [name for name in sorted(ALLOWED_FILES) if base[name] != candidate[name]]
        eligible = (not root['cancel_requested'] and root['status'] not in {'FAILED', 'CANCELLED'}
                    and plan.state not in {'NEEDS_INPUT', 'FAILED', 'CANCELLED', 'STALE', 'PUBLISHING', 'PARTIAL', 'NEEDS_RECONCILIATION'})
        new_changes = head is None or any(merged.get(name) != current[name] for name in ALLOWED_FILES)
        reason = 'plan_ineligible' if not eligible else 'conflicts' if conflicts else 'ready' if new_changes else 'no_changes'
        disposition = self._disposition(conn, project_id, plan_id)
        if eligible and disposition and disposition.status == 'DISMISSED' and disposition.source_digest == captured.source_digest:
            reason = 'dismissed'
        diff = '' if conflicts else ''.join(''.join(difflib.unified_diff(current[name].decode().splitlines(keepends=True),
            merged[name].decode().splitlines(keepends=True), fromfile='current/' + name, tofile='merged/' + name))
            for name in sorted(ALLOWED_FILES) if current[name] != merged[name])
        review = CodeIntegrationReview(project_id=project_id, plan_id=plan_id, plan_revision=plan_revision,
            project_revision=project.revision, head_revision=head.revision if head else 0,
            review_digest=digest([project.revision, plan_revision, head.model_dump(mode='json') if head else None,
                                  captured.source_digest, files_digest(base), files_digest(current),
                                  disposition.model_dump(mode='json') if disposition else None]),
            source_digest=captured.source_digest, changed_files=changed, conflict_files=conflicts, diff=diff,
            applicable=reason == 'ready', reason=reason)
        return review, plan, merged

    def review(self, project_id, plan_id, revision):
        with self.repo.db.transaction() as conn:
            return self._review(conn, project_id, plan_id, revision)[0]

    def apply(self, project_id, plan_id, data, *, authorized_until=None):
        identity = digest([project_id, plan_id, 'local-code-apply', data.client_request_id])
        request_digest = digest(data.model_dump(mode='json'))
        with self.repo.db.transaction() as conn:
            row = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='local_code_apply'"),
                               {'id': identity}).mappings().first()
            if row:
                receipt = json.loads(row['data'])
                if digest(receipt) != row['digest'] or receipt['request_digest'] != request_digest:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CommerceCodeHead.model_validate(receipt['head'])
            # Recover a committed receipt after expiry, but never create a new apply.
            if authorized_until is not None and time.time() >= authorized_until:
                raise CommerceFailure('APPROVAL_EXPIRED', project_id=project_id)
            review, plan, merged = self._review(conn, project_id, plan_id, data.expected_plan_revision)
            if not review.applicable or review.head_revision != data.expected_head_revision or review.review_digest != data.review_digest:
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w') as archive:
                for name, content in sorted(merged.items()):
                    entry = tarfile.TarInfo(name); entry.size = len(content)
                    archive.addfile(entry, io.BytesIO(content))
            try:
                artifact = SourceStore(self.source_root).seal(stream.getvalue(), project_id=project_id, plan_id=plan_id,
                                                            snapshot_hash=plan.snapshot_hash, content_hash=plan.content_hash)
            except (ValueError, OSError):
                raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id) from None
            source_id = digest([project_id, 'integrated-theme', artifact.source_digest])
            value = {'package': artifact.package.model_dump(mode='json'),
                     'archive_base64': base64.b64encode(artifact.archive).decode('ascii'), 'deployment_verified': False}
            # Include the frozen commit identity because identical bytes from different plans have different provenance.
            source_id = digest([source_id, artifact.package.code_revision])
            self._save(conn, source_id, project_id, None, 'restored_theme_source', value)
            head = CommerceCodeHead(project_id=project_id, plan_id=plan_id, source_id=source_id,
                code_revision=artifact.package.code_revision, revision=review.head_revision + 1, updated_at=time.time())
            self._save(conn, digest([project_id, 'local-code-head']), project_id, None, 'local_code_head', head.model_dump(mode='json'))
            self._save(conn, identity, project_id, plan_id, 'local_code_apply',
                       {'request_digest': request_digest, 'head': head.model_dump(mode='json')})
            previous = self._disposition(conn, project_id, plan_id)
            disposition = CodeDisposition(project_id=project_id, plan_id=plan_id, source_digest=review.source_digest,
                status='APPLIED', revision=previous.revision + 1 if previous else 1)
            self._save(conn, digest([project_id, plan_id, 'code-disposition']), project_id, plan_id, 'code_disposition', disposition.model_dump(mode='json'))
            self.repo.event(conn, project_id, 'local_code_applied', {'plan_id': plan_id, 'head_revision': head.revision,
                            'code_revision': head.code_revision, 'published': False})
            return head

    def disposition(self, project_id, plan_id, data):
        identity = digest([project_id, plan_id, 'code-decision', data.client_request_id])
        request_hash = digest(data.model_dump(mode='json'))
        with self.repo.db.transaction() as conn:
            old = conn.execute(text("SELECT data,digest FROM commerce_artifacts WHERE id=:id AND kind='code_decision_receipt'"), {'id': identity}).mappings().first()
            if old:
                receipt = json.loads(old['data'])
                if digest(receipt) != old['digest'] or receipt['request_hash'] != request_hash:
                    raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
                return CodeDisposition.model_validate(receipt['value'])
            review, _, _ = self._review(conn, project_id, plan_id, data.expected_plan_revision)
            if (review.review_digest != data.review_digest or review.head_revision != data.expected_head_revision
                    or (data.dismissed and review.reason not in {'ready', 'conflicts'})
                    or (not data.dismissed and review.reason != 'dismissed')):
                raise CommerceFailure('RESOURCE_CONFLICT', project_id=project_id)
            previous = self._disposition(conn, project_id, plan_id)
            value = CodeDisposition(project_id=project_id, plan_id=plan_id, source_digest=review.source_digest,
                status='DISMISSED' if data.dismissed else 'PENDING', revision=previous.revision + 1 if previous else 1)
            self._save(conn, digest([project_id, plan_id, 'code-disposition']), project_id, plan_id, 'code_disposition', value.model_dump(mode='json'))
            self._save(conn, identity, project_id, plan_id, 'code_decision_receipt', {'request_hash': request_hash, 'value': value.model_dump(mode='json')})
            self.repo.event(conn, project_id, 'local_code_decision', {'plan_id': plan_id, 'status': value.status, 'published': False})
            return value

    @staticmethod
    def _save(conn, identity, project_id, plan_id, kind, value):
        conn.execute(text('INSERT INTO commerce_artifacts VALUES(:id,:project,:plan,:kind,:digest,:data) '
                          'ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,data=excluded.data'),
                     {'id': identity, 'project': project_id, 'plan': plan_id, 'kind': kind, 'digest': digest(value), 'data': encode(value)})
