"""Commerce schema migration, applied atomically with the runtime schema."""
SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS commerce_projects(
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        request_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL,
        revision INTEGER NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_plans(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        request_id TEXT NOT NULL UNIQUE,request_digest TEXT NOT NULL,
        revision INTEGER NOT NULL,data TEXT NOT NULL,root_task_id TEXT REFERENCES tasks(id))''',
    '''CREATE TABLE IF NOT EXISTS commerce_snapshots(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        environment TEXT NOT NULL,digest TEXT NOT NULL,data TEXT NOT NULL,created_at REAL NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_steps(
        id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES commerce_plans(id),
        task_id TEXT REFERENCES tasks(id),revision INTEGER NOT NULL,data TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_changesets(
        id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES commerce_plans(id),
        project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        digest TEXT NOT NULL,data TEXT NOT NULL,verification TEXT)''',
    '''CREATE TABLE IF NOT EXISTS commerce_approvals(
        id TEXT PRIMARY KEY,changeset_id TEXT NOT NULL REFERENCES commerce_changesets(id),
        digest TEXT NOT NULL,status TEXT NOT NULL,expires_at REAL NOT NULL,data TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_receipts(
        operation_id TEXT PRIMARY KEY,changeset_id TEXT NOT NULL REFERENCES commerce_changesets(id),
        request_digest TEXT NOT NULL,state TEXT NOT NULL,data TEXT NOT NULL,updated_at REAL NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_artifacts(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        plan_id TEXT REFERENCES commerce_plans(id),kind TEXT NOT NULL,digest TEXT NOT NULL,data TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS commerce_events(
        project_id TEXT NOT NULL REFERENCES commerce_projects(id),sequence INTEGER NOT NULL,
        kind TEXT NOT NULL,data TEXT NOT NULL,created_at REAL NOT NULL,
        PRIMARY KEY(project_id,sequence))''',
    'INSERT OR IGNORE INTO schema_version(version) VALUES(11)',
    '''CREATE TABLE IF NOT EXISTS commerce_task_drafts(
        id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        request_id TEXT NOT NULL UNIQUE,request_digest TEXT NOT NULL,
        revision INTEGER NOT NULL,data TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS commerce_task_drafts_project_idx ON commerce_task_drafts(project_id,created_at)',
    '''CREATE TABLE IF NOT EXISTS commerce_plan_labels(
        plan_id TEXT PRIMARY KEY REFERENCES commerce_plans(id),
        project_id TEXT NOT NULL REFERENCES commerce_projects(id),
        revision INTEGER NOT NULL,title TEXT NOT NULL,updated_at REAL NOT NULL)''',
    'INSERT OR IGNORE INTO schema_version(version) VALUES(12)',
    '''CREATE TABLE IF NOT EXISTS commerce_design_versions(
        project_id TEXT NOT NULL REFERENCES commerce_projects(id), revision INTEGER NOT NULL,
        data TEXT NOT NULL, digest TEXT NOT NULL, request_id TEXT NOT NULL, request_digest TEXT NOT NULL,
        PRIMARY KEY(project_id,revision), UNIQUE(project_id,request_id))''',
    '''CREATE TABLE IF NOT EXISTS commerce_design_heads(
        project_id TEXT PRIMARY KEY REFERENCES commerce_projects(id), revision INTEGER NOT NULL)''',

]
