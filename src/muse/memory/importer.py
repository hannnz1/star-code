"""Explicit, preview-first import of StarCode Markdown notes and read-only history."""
import hashlib
import json
import re
from pathlib import Path

import yaml

from muse.permissions.secrets import contains_secret, redact

NOTE = re.compile(r"(?:user_preference|correction_feedback|project_knowledge|reference_material)_[a-z0-9_]+\.md$")


class MigrationImporter:
    def __init__(self, memory):
        self.memory = memory

    def preview_memory(self, directory: Path) -> dict:
        directory = Path(directory).resolve(strict=True)
        accepted, rejected, fingerprints = [], [], []
        for path in sorted(directory.iterdir()):
            if not NOTE.fullmatch(path.name):
                continue
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 100000:
                rejected.append({"name": path.name, "reason": "Unsafe path or oversized note"})
                continue
            raw = path.read_bytes()
            fingerprints.append([path.name, hashlib.sha256(raw).hexdigest()])
            try:
                value = raw.decode("utf-8-sig")
                match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", value, re.DOTALL)
                if not match:
                    raise ValueError("Missing front matter")
                meta = yaml.safe_load(match[1])
                title, content = str(meta["title"]).strip(), match[2].strip()
                secrets = [self.memory.settings.access_token.get_secret_value()]
                if self.memory.settings.provider:
                    secrets.append(self.memory.settings.provider.api_key.get_secret_value())
                if not title or len(title) > 160 or not content or len(content) > 12000 or contains_secret(value) or any(s and s in value for s in secrets):
                    raise ValueError("Unsafe or invalid note")
                accepted.append({"name": path.name, "title": title, "content": content})
            except (ValueError, KeyError, TypeError, yaml.YAMLError):
                rejected.append({"name": path.name, "reason": "Unsafe or invalid note"})
        digest = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
        return {"digest": digest, "accepted": accepted, "rejected": rejected}

    def import_memory(self, directory, digest, *, scope, workspace_id=None):
        preview = self.preview_memory(directory)
        if preview["digest"] != digest:
            raise ValueError("Import source changed after preview")
        existing = {item["id"] for item in self.memory.list()}
        imported = []
        for item in preview["accepted"]:
            identifier = hashlib.sha256(f"{Path(directory).resolve()}|{item['name']}|{scope}|{workspace_id}".encode()).hexdigest()[:32]
            if identifier in existing:
                continue  # Newer edited MUSE notes take precedence over repeat imports.
            record = self.memory.upsert(scope=scope, workspace_id=workspace_id, title=item["title"], content=item["content"])
            from sqlalchemy import text
            with self.memory.repo.db.transaction() as conn:
                conn.execute(text("UPDATE memories SET id=:new WHERE id=:old"), {"new": identifier, "old": record["id"]})
            imported.append(identifier)
        return {"imported": imported, "rejected": preview["rejected"]}


def preview_history(path: Path, secrets=()) -> dict:
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("History file is unsafe or too large")
    lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            lines.append("## " + item["role"] + "\n\n" + redact(item["content"], secrets))
    return {"resumable": False, "markdown": "# Imported StarCode history (read-only)\n\n" + "\n\n".join(lines)}
