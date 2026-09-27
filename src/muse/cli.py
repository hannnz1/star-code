import argparse
import asyncio
import json
import os
from pathlib import Path

from muse.config import load_settings


def main():
    parser = argparse.ArgumentParser(prog="muse", description="MUSE personal task assistant")
    parser.add_argument("command", choices=["api", "worker", "terminal", "tui", "doctor", "token", "probe", "import-memory", "import-history", "backup-state", "restore-state"])
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, help="Explicit StarCode/MUSE provider configuration")
    parser.add_argument("--provider", help="Provider name within that configuration")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--apply-digest", help="Apply an unchanged memory import after reviewing its preview")
    parser.add_argument("--scope", choices=["user", "project"], default="project")
    parser.add_argument("--workspace-id")
    parser.add_argument("--output", type=Path, help="Explicit new Markdown history archive path")
    args = parser.parse_args()
    try:
        if args.command == 'restore-state':
            from muse.storage.backup import restore_state
            if not args.source or not args.data_dir:
                raise ValueError('Restore requires --source ARCHIVE and --data-dir NEW_DIRECTORY')
            print(json.dumps(restore_state(args.source, args.data_dir), ensure_ascii=False, indent=2))
            return
        settings = load_settings(args.config, provider_name=args.provider, data_dir=args.data_dir,
                                 require_provider=args.command in {"worker", "probe"})
        settings.port = args.port
        settings.allowed_origins.extend([f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"])
        browsers = Path(__file__).resolve().parents[2] / "work" / "browsers"
        if browsers.is_dir():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
        if args.command == 'backup-state':
            from muse.storage.backup import backup_state
            if not args.output:
                raise ValueError('Backup requires --output NEW_ARCHIVE')
            print(json.dumps(backup_state(settings.data_dir, args.output), ensure_ascii=False, indent=2))
        elif args.command == 'tui':
            from muse.tui import run_tui
            run_tui(settings, args.workspace)
        elif args.command == 'terminal':
            from muse.terminal import run_terminal
            run_terminal(settings, args.workspace)
        elif args.command in {"import-memory", "import-history"}:
            from muse.memory.importer import MigrationImporter, preview_history
            from muse.memory.service import MemoryService
            from muse.tasks.repository import TaskRepository
            if not args.source:
                raise ValueError("Import requires --source")
            if args.command == "import-history":
                secrets = [settings.access_token.get_secret_value()]
                if settings.provider:
                    secrets.append(settings.provider.api_key.get_secret_value())
                preview = preview_history(args.source, secrets)
                if args.output:
                    with args.output.open("x", encoding="utf-8") as stream:
                        stream.write(preview["markdown"])
                    print("Read-only history archive created; no executable task was imported.")
                else:
                    print(preview["markdown"])
            else:
                importer = MigrationImporter(MemoryService(TaskRepository(settings.data_dir / "state.sqlite3"), settings))
                result = importer.import_memory(args.source, args.apply_digest, scope=args.scope, workspace_id=args.workspace_id) if args.apply_digest else importer.preview_memory(args.source)
                print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "doctor":
            print(json.dumps(settings.public(), ensure_ascii=False, indent=2))
        elif args.command == "token":
            print(settings.access_token.get_secret_value())
        elif args.command == "api":
            import uvicorn

            from muse.main import create_app
            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)
        else:
            from muse.providers.compatible import HttpModelProvider
            provider = HttpModelProvider(settings.provider)
            if args.command == "probe":
                async def probe():
                    chunks = []
                    async for event in provider.stream([{"role": "user", "content": "Reply exactly MUSE_OK. Do not call tools."}], []):
                        if event.type == "text":
                            chunks.append(event.text)
                    print(json.dumps({"model": settings.provider.model, "protocol": settings.provider.protocol,
                                      "ok": "MUSE_OK" in "".join(chunks)}, ensure_ascii=False))
                asyncio.run(probe())
            else:
                from muse.agent.loop import AgentRunner
                from muse.tasks.repository import TaskRepository
                from muse.tasks.worker import Worker
                repo = TaskRepository(settings.data_dir / "state.sqlite3")
                asyncio.run(Worker(settings, repo, AgentRunner(provider)).run_forever())
    except (ValueError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
