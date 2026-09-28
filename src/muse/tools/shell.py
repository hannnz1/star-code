import asyncio
import os
import shutil
import sys
from pathlib import Path

import psutil

from muse.artifacts.service import ArtifactService
from muse.contracts import ToolResult
from muse.tools.process_tree import ProcessTree


def stop_tree(pid: int):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for process in reversed(children):
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        psutil.wait_procs(children + [parent], timeout=2)
    except psutil.NoSuchProcess:
        pass


async def run_command(context, args, call_id: str, *, verify: bool = False, argv: list[str] | None = None,
                      machine_output: bool = False) -> ToolResult:
    context.check()
    command = args["command"]
    shell = shutil.which("pwsh") or shutil.which("powershell") if os.name == "nt" else shutil.which("bash")
    if not shell:
        raise ValueError("No supported command shell is installed")
    options = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command"] if os.name == "nt" else ["-c"]
    environment = {key: value for key, value in os.environ.items() if key.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "NUMBER_OF_PROCESSORS",
    }}
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    temp = context.settings.data_dir.parent / (context.settings.data_dir.name + '-process-temp') / context.task_id
    temp.mkdir(parents=True, exist_ok=True)
    environment.update(TEMP=str(temp), TMP=str(temp), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    from muse.permissions.os_sandbox import sandbox_argv
    effective_argv = sandbox_argv(context, argv if argv is not None else [shell, *options, command], temp)
    context.save()
    process = await asyncio.create_subprocess_exec(*effective_argv, cwd=context.workspace, env=environment,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **ProcessTree.launch_options())
    try:
        tree = ProcessTree(process.pid)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise

    async def drain(stream):
        chunks = bytearray()
        truncated = False
        while data := await stream.read(8192):
            remaining = max(0, 120000 - len(chunks))
            chunks.extend(data[:remaining])
            truncated |= len(data) > remaining
        return chunks.decode("utf-8", errors="replace") + ("\n[output truncated]" if truncated else "")

    output = asyncio.create_task(drain(process.stdout))
    errors = asyncio.create_task(drain(process.stderr))
    async def lifecycle():
        # Process.wait can remain blocked by pipes inherited by exited parents' children.
        while process.returncode is None:
            await asyncio.sleep(0.02)
        tree.close()
        captured = await asyncio.gather(output, errors)
        await process.wait()
        return captured
    try:
        timeout = min(float(args.get("timeout_seconds", 120)), 300)
        stdout, stderr = await context.controlled(asyncio.wait_for(lifecycle(), timeout=timeout))
    except BaseException:
        tree.close()
        try:
            await asyncio.wait_for(asyncio.gather(process.wait(), output, errors, return_exceptions=True), timeout=2)
        except TimeoutError:
            output.cancel()
            errors.cancel()
        raise
    finally:
        tree.close()
    safe = context.safe(stdout + ("\n[stderr]\n" + stderr if stderr else ""))
    log_dir = context.settings.data_dir / "command-logs" / context.task_id
    log_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    log = log_dir / (hashlib.sha256(call_id.encode()).hexdigest() + ".txt")
    log.write_text(safe, encoding="utf-8")
    artifact = ArtifactService(context).save("command-" + hashlib.sha256(call_id.encode()).hexdigest()[:12] + ".txt", safe.encode("utf-8"), "text/plain")
    metadata = {"exit_code": process.returncode, "verified": verify, "log_path": str(log)}
    if verify:
        from muse.tools.verification import mutation_ids
        metadata["mutation_call_ids"] = sorted(mutation_ids(context.repo.calls(context.task_id)))
        context.cp["verification"] = {**metadata, "call_id": call_id}
    return ToolResult(call_id=call_id, status="success" if process.returncode == 0 else "error",
                      content=stdout if machine_output and process.returncode == 0 else safe,
                      artifact_ids=[artifact["id"]], error_code=None if process.returncode == 0 else "COMMAND_FAILED", metadata=metadata)
