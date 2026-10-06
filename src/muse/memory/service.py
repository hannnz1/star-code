import json
import re
import time
import uuid

from sqlalchemy import text

from muse.permissions.secrets import contains_secret


class MemoryService:
    def __init__(self, repository, settings):
        self.repo, self.settings = repository, settings
        with repository.db.transaction() as conn:
            conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS memories(
                id TEXT PRIMARY KEY,scope TEXT NOT NULL,workspace_id TEXT REFERENCES workspaces(id),
                title TEXT NOT NULL,content TEXT NOT NULL,source_task_id TEXT,updated_at REAL NOT NULL)""")
            columns = {row[1] for row in conn.exec_driver_sql('PRAGMA table_info(memories)')}
            for name, datatype in [('version', 'INTEGER NOT NULL DEFAULT 1'), ('status', "TEXT NOT NULL DEFAULT 'active'"),
                                   ('provenance', "TEXT NOT NULL DEFAULT 'legacy/manual'"), ('conflict_id', 'TEXT')]:
                if name not in columns:
                    conn.exec_driver_sql(f'ALTER TABLE memories ADD COLUMN {name} {datatype}')
            conn.exec_driver_sql('CREATE TABLE IF NOT EXISTS memory_versions(memory_id TEXT NOT NULL,version INTEGER NOT NULL,record TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(memory_id,version))')
            for row in conn.execute(text('SELECT * FROM memories')).mappings():
                conn.execute(text('INSERT OR IGNORE INTO memory_versions VALUES(:id,:version,:record,:now)'),
                             {'id': row['id'], 'version': row['version'], 'record': json.dumps(dict(row)), 'now': row['updated_at']})

    def upsert(self, *, scope: str, content: str, title: str, workspace_id: str | None = None,
               memory_id: str | None = None, source_task_id: str | None = None,
               status: str = 'active', provenance: str = 'manual', conflict_id: str | None = None) -> dict:
        if status not in {'active', 'candidate', 'superseded', 'withdrawn'}:
            raise ValueError('Invalid memory status')
        if scope not in {"user", "project"} or not title.strip() or len(title) > 160 or not content.strip() or len(content) > 12000:
            raise ValueError("Invalid memory fields")
        secrets = [self.settings.access_token.get_secret_value()]
        if self.settings.provider:
            secrets.append(self.settings.provider.api_key.get_secret_value())
        if self.settings.commerce_connector:
            secrets.append(self.settings.commerce_connector.token.get_secret_value())
        if contains_secret(content) or contains_secret(title) or any(s and s in content + title for s in secrets):
            raise ValueError("Memory cannot contain secrets")
        if scope == "project":
            self.repo.workspace(workspace_id)
        elif workspace_id is not None:
            raise ValueError("User memory must not have a workspace")
        record = {"id": memory_id or uuid.uuid4().hex, "scope": scope, "workspace_id": workspace_id,
                  "title": title.strip(), "content": content.strip(), "source_task_id": source_task_id, "updated_at": time.time(),
                  'status': status, 'provenance': provenance, 'conflict_id': conflict_id, 'version': 1}
        with self.repo.db.transaction() as conn:
            if memory_id:
                old = conn.execute(text('SELECT * FROM memories WHERE id=:id'), {'id': memory_id}).mappings().first()
                if not old:
                    raise ValueError('Unknown memory')
                record['version'] = old['version'] + 1
            conn.execute(text("""INSERT INTO memories(id,scope,workspace_id,title,content,source_task_id,updated_at,version,status,provenance,conflict_id)
                VALUES(:id,:scope,:workspace_id,:title,:content,:source_task_id,:updated_at,:version,:status,:provenance,:conflict_id)
                ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,workspace_id=excluded.workspace_id,title=excluded.title,
                content=excluded.content,source_task_id=excluded.source_task_id,updated_at=excluded.updated_at,
                version=excluded.version,status=excluded.status,provenance=excluded.provenance,conflict_id=excluded.conflict_id"""), record)
            conn.execute(text('INSERT INTO memory_versions VALUES(:id,:version,:record,:now)'),
                         {'id': record['id'], 'version': record['version'], 'record': json.dumps(record), 'now': record['updated_at']})
        return record

    def for_task(self, workspace_id: str) -> list[dict]:
        return self.repo.db.rows("SELECT * FROM memories WHERE status='active' AND (scope='user' OR (scope='project' AND workspace_id=:ws)) ORDER BY updated_at DESC,id LIMIT 100", {"ws": workspace_id})

    def delete(self, memory_id: str):
        self._transition(memory_id, 'withdrawn')

    def list(self) -> list[dict]:
        return self.repo.db.rows("SELECT * FROM memories WHERE status='active' ORDER BY updated_at DESC")

    def candidates(self):
        return self.repo.db.rows("SELECT * FROM memories WHERE status='candidate' ORDER BY updated_at DESC")

    def history(self, memory_id):
        return [json.loads(row['record']) for row in self.repo.db.rows(
            'SELECT record FROM memory_versions WHERE memory_id=:id ORDER BY version', {'id': memory_id})]

    def _transition(self, memory_id, status):
        rows = self.repo.db.rows('SELECT * FROM memories WHERE id=:id', {'id': memory_id})
        if not rows:
            raise ValueError('Unknown memory')
        record = rows[0]
        return self.upsert(**{key: record[key] for key in ('scope', 'workspace_id', 'title', 'content', 'source_task_id', 'provenance', 'conflict_id')},
                           memory_id=memory_id, status=status)

    def confirm(self, memory_id):
        record = next((row for row in self.candidates() if row['id'] == memory_id), None)
        if not record:
            raise ValueError('Unknown memory candidate')
        if record['conflict_id']:
            self._transition(record['conflict_id'], 'superseded')
        return self._transition(memory_id, 'active')

    def recall(self, workspace_id, query):
        terms = set(re.findall(r'\w+', query.casefold()))
        rows = self.for_task(workspace_id)
        rows.sort(key=lambda row: (-len(terms & set(re.findall(r'\w+', (row['title'] + ' ' + row['content']).casefold()))),
                                   -row['updated_at'], row['id']))
        return rows[:self.settings.memory_recall_top_k]

    def projection(self, workspace_id, selected, *, mode):
        candidates = self.for_task(workspace_id)
        active = {record['id']: record for record in candidates}
        projected, used, excluded = [], 0, []
        for record in selected:
            if record['id'] not in active:
                excluded.append({'id': record['id'], 'reason': 'withdrawn_or_out_of_scope'})
                continue
            item = {key: active[record['id']][key] for key in ('id', 'title', 'content', 'scope', 'version', 'status', 'provenance', 'updated_at')}
            item['content_truncated'] = len(item['content']) > 4000
            item['content'] = item['content'][:4000]
            item['provenance'] = item['provenance'][:2000]
            size = len(json.dumps(item, ensure_ascii=False))
            if used + size > 24000:
                excluded.append({'id': item['id'], 'reason': 'context_quota'})
                continue
            used += size
            projected.append(item)
        selected_ids = {record['id'] for record in projected}
        excluded += [{'id': record['id'], 'reason': 'not_selected'} for record in candidates
                     if record['id'] not in selected_ids and record['id'] not in {row['id'] for row in excluded}]
        return projected, {'mode': mode, 'fallback': mode == 'local_fallback', 'candidate_limit': 100,
                           'candidate_count': len(candidates), 'injection_limit': 10,
                           'selected': [{'id': row['id'], 'version': row['version'], 'content_truncated': row['content_truncated']} for row in projected],
                           'excluded': excluded, 'context_chars': used}
