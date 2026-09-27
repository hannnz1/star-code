import os
from pathlib import Path


class WorkspacePolicy:
    def __init__(self, root: Path, protected: list[Path] | None = None):
        registered = Path(os.path.abspath(root))
        resolved = registered.resolve(strict=True)
        if registered != resolved or registered.is_symlink() or (hasattr(registered, "is_junction") and registered.is_junction()):
            raise PermissionError("Registered workspace path was replaced by a link")
        self.root = registered
        self.protected = [p.resolve() for p in (protected or [])]

    def resolve(self, value: str, *, must_exist: bool = False) -> Path:
        if self.root.resolve(strict=True) != self.root or self.root.is_symlink() or (hasattr(self.root, "is_junction") and self.root.is_junction()):
            raise PermissionError("Workspace root was replaced by a link")
        if not value or "\x00" in value:
            raise PermissionError("Invalid workspace path")
        raw = Path(value)
        if ".." in raw.parts:
            raise PermissionError("Parent traversal is not permitted")
        candidate = raw if raw.is_absolute() else self.root / raw
        candidate = Path(os.path.abspath(candidate))
        if not candidate.is_relative_to(self.root):
            raise PermissionError("Path is outside the task workspace")
        relative = candidate.relative_to(self.root)
        for name in relative.parts:
            lower = name.lower()
            if lower.startswith(".env") or lower in {".git", ".muse", ".mewcode", ".ssh", "credentials.json", "id_rsa", "id_ed25519", "access-token"}:
                raise PermissionError("Sensitive paths are not available to tools")
            if os.name == "nt" and ":" in name:
                raise PermissionError("Alternate data streams are not allowed")
        cursor = self.root
        for name in relative.parts:
            cursor = cursor / name
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise PermissionError("Symbolic links and junctions are not available to file tools")
        resolved = candidate.resolve(strict=must_exist)
        if not resolved.is_relative_to(self.root):
            raise PermissionError("Resolved path escapes the workspace")
        if any(resolved == p or resolved.is_relative_to(p) for p in self.protected):
            raise PermissionError("Application state and credentials are protected")
        return resolved
