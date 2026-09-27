"""Test-only crash barrier. Never imported by the production CLI."""
import argparse
import asyncio
from pathlib import Path

from muse.agent.loop import AgentRunner
from muse.config import load_settings
from muse.providers.compatible import HttpModelProvider
from muse.tasks.repository import TaskRepository
from muse.tasks.worker import Worker
from muse.tools.registry import ToolRegistry


async def run(args):
    settings = load_settings(args.config, data_dir=args.data)
    settings.lease_seconds, settings.heartbeat_seconds = 2, .3
    repo = TaskRepository(settings.data_dir / "state.sqlite3")
    class BarrierRegistry(ToolRegistry):
        def __init__(self, context):
            super().__init__(context)
            name = "read_file" if args.mode == "read" else "write_file"
            definition, handler = self.entries[name]
            async def blocked(arguments, call_id):
                result = await handler(arguments, call_id)
                if args.mode == "write" or arguments.get("path") == "two.txt":
                    counter = Path(args.barrier).with_suffix(".count")
                    counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else "1")
                    Path(args.barrier).write_text("committed-before-result")
                    await asyncio.sleep(120)
                return result
            self.entries[name] = (definition, blocked)
    worker = Worker(settings, repo, AgentRunner(HttpModelProvider(settings.provider), BarrierRegistry))
    await worker.run_once()


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    for name in ("config","data","barrier","mode"): parser.add_argument("--"+name,required=True)
    asyncio.run(run(parser.parse_args()))
