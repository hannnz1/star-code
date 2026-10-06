import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.parametrize('matching_time,race_after_lookup', [(True, False), (False, False), (True, True)])
def test_stop_script_matches_serialized_process_time(tmp_path, matching_time, race_after_lookup):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell, "PowerShell is required for Windows launcher tests"
    script = Path(__file__).resolve().parents[3] / "Stop-MUSE.ps1"
    shutil.copy2(script, tmp_path / script.name)
    if race_after_lookup:
        copied = tmp_path / script.name
        source = copied.read_text(encoding='utf-8-sig')
        command = '[MuseOwnedProcessTree]::Stop([uint32]$entry.pid, ([datetime]$entry.started).ToUniversalTime().ToFileTimeUtc())'
        assert command in source
        # Deterministically simulate the matched, test-owned process exiting
        # just before the native tree stopper opens its process handle.
        copied.write_text(source.replace(command, 'Stop-Process -Id $entry.pid -Force\n        ' + command), encoding='utf-8')
    state = tmp_path / ".muse"
    state.mkdir()
    child = subprocess.Popen([sys.executable, "-c", "import threading; threading.Event().wait()"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        timestamp = subprocess.run([shell, "-NoProfile", "-Command", f"(Get-Process -Id {child.pid}).StartTime.ToUniversalTime().ToString('o')"], capture_output=True, text=True, check=True).stdout.strip()
        (state / "processes.json").write_text(json.dumps([{"pid": child.pid, "role": "fixture", "started": timestamp if matching_time else "2000-01-01T00:00:00.0000000Z"}]), encoding="utf-8")
        stopped = subprocess.run([shell, "-NoProfile", "-File", str(tmp_path / script.name)], capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert (child.poll() is not None) == matching_time, stopped.stdout
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


@pytest.mark.parametrize('exit_after_hold', [False, True])
def test_stop_script_terminates_managed_descendants_together(tmp_path, exit_after_hold):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    assert shell
    script = Path(__file__).resolve().parents[3] / 'Stop-MUSE.ps1'
    shutil.copy2(script, tmp_path / script.name)
    if exit_after_hold:
        copied = tmp_path / script.name
        source = copied.read_text(encoding='utf-8-sig')
        command = '[MuseOwnedProcessTree]::Stop([uint32]$entry.pid, ([datetime]$entry.started).ToUniversalTime().ToFileTimeUtc())'
        assert command in source
        copied.write_text(source.replace(command, 'Stop-Process -Id $entry.pid -Force\n        ' + command), encoding='utf-8')
    state = tmp_path / '.muse'
    state.mkdir()
    pidfile = tmp_path / 'child-pid'
    program = ('import subprocess,sys,threading,pathlib; '
               'child=subprocess.Popen([sys.executable,"-c","import threading; threading.Event().wait()"]); '
               'pathlib.Path(sys.argv[1]).write_text(str(child.pid)); threading.Event().wait()')
    parent = subprocess.Popen([sys.executable, '-c', program, str(pidfile)])
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        child_pid = int(pidfile.read_text())
        timestamp = subprocess.run([shell, '-NoProfile', '-Command',
            f"(Get-Process -Id {parent.pid}).StartTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, check=True).stdout.strip()
        (state / 'processes.json').write_text(json.dumps([{'pid': parent.pid, 'role': 'fixture-tree', 'started': timestamp}]))
        stopped = subprocess.run([shell, '-NoProfile', '-File', str(tmp_path / script.name)], capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', check=False)
        assert stopped.returncode == 0, stopped.stderr
        parent.wait(timeout=5)
        exists = subprocess.run([shell, '-NoProfile', '-Command',
                                f'if (Get-Process -Id {child_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}'],
                               capture_output=True, check=False)
        assert exists.returncode == 0, 'A managed descendant was left running'
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=10)
        if child_pid is not None:
            subprocess.run([shell, '-NoProfile', '-Command',
                            f'Stop-Process -Id {child_pid} -Force -ErrorAction SilentlyContinue'], capture_output=True, check=False)


def test_stop_script_rechecks_child_parent_after_opening_handle(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    assert shell
    script = Path(__file__).resolve().parents[3] / 'Stop-MUSE.ps1'
    managed = subprocess.Popen([sys.executable, '-c', 'import threading; threading.Event().wait()'])
    foreign = subprocess.Popen([sys.executable, '-c', 'import threading; threading.Event().wait()'])
    try:
        timestamp = subprocess.run([shell, '-NoProfile', '-Command',
            f"(Get-Process -Id {managed.pid}).StartTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, check=True).stdout.strip()
        # Simulate a stale child snapshot whose PID was reused by an unrelated
        # process before the handle was opened. Both processes are test-owned.
        source = script.read_text(encoding='utf-8-sig')
        old = 'var children = Children(pid);'
        assert old in source
        source = source.replace(old, 'var children = new List<uint> { ' + str(foreign.pid) + ' };', 1)
        (tmp_path / script.name).write_text(source, encoding='utf-8')
        state = tmp_path / '.muse'
        state.mkdir()
        (state / 'processes.json').write_text(json.dumps([{'pid': managed.pid, 'role': 'fixture', 'started': timestamp}]))
        assert managed.poll() is None and foreign.poll() is None
        stopped = subprocess.run([shell, '-NoProfile', '-File', str(tmp_path / script.name)], capture_output=True, check=False)
        assert stopped.returncode != 0
        assert foreign.poll() is None, 'An unrelated process was terminated'
        assert managed.poll() is None, 'Identity rejection must precede termination'
    finally:
        for process in (managed, foreign):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def test_stop_script_waits_for_exit_when_termination_is_already_in_progress(tmp_path, monkeypatch):
    copy = shutil.copy2
    def inject(source, destination):
        result = copy(source, destination)
        target = Path(destination)
        script = target.read_text(encoding='utf-8-sig')
        old = '[DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr handle, uint code);'
        new = '''[DllImport("kernel32.dll", EntryPoint="TerminateProcess", SetLastError=true)] static extern bool NativeTerminateProcess(IntPtr handle, uint code);
    static bool pendingExit;
    static bool TerminateProcess(IntPtr handle, uint code) {
        bool result = NativeTerminateProcess(handle, code);
        if (result) { pendingExit = true; return false; }
        return result;
    }'''
        assert old in script
        script = script.replace(old, new)
        old = '[DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint timeout);'
        new = '''[DllImport("kernel32.dll", EntryPoint="WaitForSingleObject")] static extern uint NativeWaitForSingleObject(IntPtr handle, uint timeout);
    static uint WaitForSingleObject(IntPtr handle, uint timeout) {
        // Deterministically model the short interval before a terminating
        // process handle signals. The real test-owned process is terminated.
        if (timeout == 0 && pendingExit) { pendingExit = false; return 258; }
        return NativeWaitForSingleObject(handle, timeout);
    }'''
        assert old in script
        target.write_text(script.replace(old, new), encoding='utf-8')
        return result
    monkeypatch.setattr(shutil, 'copy2', inject)
    test_stop_script_matches_serialized_process_time(tmp_path, True, False)


def test_stop_script_does_not_ignore_denied_termination_of_live_process(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    assert shell
    script = Path(__file__).resolve().parents[3] / 'Stop-MUSE.ps1'
    source = script.read_text(encoding='utf-8-sig')
    old = '[DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr handle, uint code);'
    assert old in source
    target = tmp_path / script.name
    target.write_text(source.replace(old, 'static bool TerminateProcess(IntPtr handle, uint code) { return false; }'), encoding='utf-8')
    state = tmp_path / '.muse'
    state.mkdir()
    child = subprocess.Popen([sys.executable, '-c', 'import threading; threading.Event().wait()'])
    try:
        stamp = subprocess.run([shell, '-NoProfile', '-Command',
            f"(Get-Process -Id {child.pid}).StartTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, check=True).stdout.strip()
        (state / 'processes.json').write_text(json.dumps([{'pid': child.pid, 'role': 'denied-fixture', 'started': stamp}]))
        result = subprocess.run([shell, '-NoProfile', '-File', str(target)], capture_output=True, check=False)
        assert result.returncode != 0 and child.poll() is None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
