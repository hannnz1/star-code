"""Compatibility command names backed exclusively by the durable MUSE service."""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import httpx

from muse.config import load_settings
from muse.contracts import TERMINAL
from muse.terminal import connect_terminal


def execute_prompt(terminal, prompt, *, output_format='text', wait_seconds=300, read_only=False, permission_mode='default'):
    terminal.submit(prompt, read_only=read_only, permission_mode='plan' if read_only else permission_mode)
    deadline = time.monotonic() + wait_seconds
    cursor = 0
    previous = None
    waiting = {'WAITING_APPROVAL', 'WAITING_INPUT', 'PAUSED', 'INTERRUPTED'}
    while True:
        task = terminal.task()
        if output_format == 'stream-json':
            while True:
                response = terminal.client.get(f"/api/tasks/{task['id']}/events", params={'follow': 'false', 'after': cursor})
                response.raise_for_status()
                received = 0
                for line in response.text.splitlines():
                    if line.startswith('data: '):
                        event = json.loads(line[6:])
                        cursor = max(cursor, event['sequence'])
                        received += 1
                        print(json.dumps({'type': 'event', 'event': event}, ensure_ascii=False), flush=True)
                # Stopped tasks must drain the paginated endpoint before exit.
                # Active tasks poll again without starving the wait deadline.
                if received == 0 or task['status'] not in TERMINAL | waiting:
                    break
            if task != previous:
                print(json.dumps({'type': 'task', 'task': task}, ensure_ascii=False), flush=True)
        elif previous is None:
            print(f"MUSE task: {task['id']}", flush=True)
        previous = task
        if task['status'] in TERMINAL:
            if output_format == 'text':
                print(task['result'] or task['error'] or task['status'], flush=True)
            return 0 if task['status'] == 'SUCCEEDED' else 1
        if task['status'] in waiting:
            if output_format == 'text':
                print(f"{task['status']}: continue this task in the web UI or terminal /use {task['id']}", flush=True)
            return 2
        if time.monotonic() >= deadline:
            if output_format == 'text':
                print('Wait deadline reached; the task remains in the background queue.', flush=True)
            return 3
        time.sleep(min(.5, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(prog='mewcode', description='MUSE compatibility entry; start API and Worker with Start-MUSE.ps1 first.')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--provider')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('-p', metavar='PROMPT')
    parser.add_argument('--output-format', choices=['text', 'stream-json'], default='text')
    parser.add_argument('--wait-seconds', type=float, default=300)
    parser.add_argument('--mode', choices=['default', 'acceptEdits', 'plan'], default='default',
                        help='default approves writes and execution; acceptEdits permits workspace edits; plan permits read tools only')
    parser.add_argument('--remote', action='store_true', help='Run the loopback MUSE web API; Worker is started separately')
    args = parser.parse_args()
    if not math.isfinite(args.wait_seconds) or args.wait_seconds < 0:
        parser.error('--wait-seconds must be finite and nonnegative')
    if args.remote and args.p is not None:
        parser.error('--remote and -p are mutually exclusive')
    if args.mode == 'plan' and args.p is None:
        parser.error('Use -p with --mode plan, or /plan in the terminal')
    try:
        settings = load_settings(args.config, provider_name=args.provider, data_dir=args.data_dir, require_provider=False)
        settings.port = args.port
        if args.remote:
            import uvicorn

            from muse.main import create_app
            settings.allowed_origins.extend([f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}'])
            uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port, access_log=False)
        elif args.p is not None:
            with connect_terminal(settings, args.workspace) as terminal:
                raise SystemExit(execute_prompt(terminal, args.p, output_format=args.output_format,
                                               wait_seconds=args.wait_seconds, permission_mode=args.mode))
        else:
            from muse.tui import run_tui
            run_tui(settings, args.workspace, permission_mode=args.mode)
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        parser.exit(1, f'{error}\nCheck that API and Worker use the same --data-dir, --port and original configuration.\n')
    except KeyboardInterrupt:
        print('Client closed; existing tasks continue in the Worker.', file=sys.stderr)
        raise SystemExit(130) from None
