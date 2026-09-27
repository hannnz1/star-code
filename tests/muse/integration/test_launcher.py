import json
import shutil
import subprocess
import sys
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
        command = '& "$env:SystemRoot\\System32\\taskkill.exe" /PID $entry.pid /T /F | Out-Null'
        assert command in source
        # Deterministically simulate the matched, test-owned process exiting
        # just before taskkill returns its nonzero "not running" status.
        copied.write_text(source.replace(command, 'Stop-Process -Id $entry.pid -Force\n        $global:LASTEXITCODE = 128'), encoding='utf-8')
    state = tmp_path / ".muse"
    state.mkdir()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        timestamp = subprocess.run([shell, "-NoProfile", "-Command", f"(Get-Process -Id {child.pid}).StartTime.ToUniversalTime().ToString('o')"], capture_output=True, text=True, check=True).stdout.strip()
        (state / "processes.json").write_text(json.dumps([{"pid": child.pid, "role": "fixture", "started": timestamp if matching_time else "2000-01-01T00:00:00.0000000Z"}]), encoding="utf-8")
        stopped = subprocess.run([shell, "-NoProfile", "-File", str(tmp_path / script.name)], capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert (child.poll() is not None) == matching_time, stopped.stdout
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
