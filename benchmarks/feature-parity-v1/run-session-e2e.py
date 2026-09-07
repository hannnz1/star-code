"""Run the packaged CLI against a scripted loopback SSE fixture, without core edits.

This is application integration evidence, NOT real-provider/model capability evidence.
The driver only types user commands; production code must perform every file mutation
and rewind. Results, fixture, HTTP bodies and terminal output remain on disk.
"""
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S-%fZ')
OUT = ROOT / 'benchmarks/results/raw/feature-parity-session-v1' / RUN

def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def main():
    OUT.mkdir(parents=True)
    work = OUT / 'workspace'
    home = OUT / 'isolated-home'
    work.mkdir()
    home.mkdir()
    (work / 'existing.txt').write_text('before', encoding='utf-8')
    (work / '.starcode').mkdir()
    # Exact fixture paths only; the normal production permission pipeline remains active.
    (work / '.starcode/permissions.yaml').write_text(
        'allow:\n  - Edit(existing.txt)\n  - Write(created.txt)\n', encoding='utf-8')
    jar = ROOT / 'build/libs/star-code.jar'
    accepted = json.loads((ROOT / 'benchmarks/results/feature-parity-accepted.json').read_text(encoding='utf-8'))
    jar_hash = hashlib.sha256(jar.read_bytes()).hexdigest()
    require(accepted['status'] == 'PASS' and jar_hash == accepted['jar_sha256'], 'Accepted package gate required')
    calls = [
        dict(index=0, id='edit-fixture', type='function', function=dict(name='edit_file', arguments=json.dumps(dict(path='existing.txt', old_text='before', new_text='after')))),
        dict(index=1, id='write-fixture', type='function', function=dict(name='write_file', arguments=json.dumps(dict(path='created.txt', content='created'))))]
    fixture = [
        dict(choices=[dict(index=0, delta=dict(tool_calls=calls), finish_reason='tool_calls')]),
        dict(choices=[dict(index=0, delta=dict(content='FIXTURE_EDIT_COMPLETE'), finish_reason='stop')]),
        dict(choices=[dict(index=0, delta=dict(content='FIXTURE_CONTEXT_CHECKED'), finish_reason='stop')])]
    save(OUT / 'fixture.json', fixture)
    record = dict(benchmark='feature-parity-session-v1', run_id=RUN, timestamp=datetime.now(timezone.utc).isoformat(),
                  status='FAILURE', seed=0, model='SCRIPTED_LOCAL_FIXTURE', protocol='openai-compat',
                  model_configuration={'thinking': False, 'context_window': 128000},
                  os=platform.platform(), java=subprocess.check_output(['java', '--version'], text=True),
                  git_commit=subprocess.check_output(['git', '-c', 'safe.directory='+ROOT.as_posix(), 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  jar_sha256=jar_hash, usage={'input': None, 'output': None, 'total': None, 'method': 'no usage in scripted fixture'},
                  paid_model_calls=0, retries=0, checks=[], limitations=['Scripted model; not provider interoperability or coding quality',
                  'No concurrent subagents, worktree session switching or UI resume covered'])
    requests = []
    errors = []
    server = None
    process = None
    started = time.monotonic()
    terminal = bytearray()
    events = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            index = len(requests)
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            save(OUT / f'request-{index+1}.json', body)
            try:
                require(self.path == '/v1/chat/completions', 'Wrong production endpoint')
                require(index < len(fixture), 'Unexpected model call')
                require(body.get('stream') is True and body.get('model') == 'fixture', 'Wrong serialized model configuration')
                if index == 1:
                    results = [m for m in body['messages'] if m['role'] == 'tool']
                    require({m['tool_call_id'] for m in results} == {'edit-fixture', 'write-fixture'}, 'Tool results not returned through model client')
                if index == 2:
                    require(not any(m['role'] in ('tool', 'assistant') for m in body['messages']), 'Rewound messages leaked into next model request')
                    require(not any('EDIT_FIXTURE' in m.get('content', '') for m in body['messages']), 'Original user turn was not rewound')
                response = fixture[index]
                payload = ('data: '+json.dumps(response)+'\n\ndata: [DONE]\n\n').encode()
                (OUT / f'response-{index+1}.sse').write_bytes(payload)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as error:
                errors.append(str(error))
                self.send_error(500, 'Fixture assertion failed')

    def wait_prompt(offset, marker=''):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            text = bytes(terminal).decode('utf-8', errors='replace')
            require(process.poll() is None, 'CLI exited before expected prompt: '+text[-1200:])
            require(not errors, '; '.join(errors))
            # Windows dumb terminals may encode the Unicode prompt as a literal '?'.
            segment = text[offset:]
            if marker and marker not in segment:
                time.sleep(0.05)
                continue
            tail = segment[segment.rfind(marker)+len(marker):] if marker else segment
            if tail.rstrip().endswith('❯') or tail.rstrip().endswith('\n?'):
                return text[offset:]
            time.sleep(0.05)
        raise TimeoutError('No next CLI prompt; inspect terminal.log')

    def command(value):
        offset = len(bytes(terminal).decode('utf-8', errors='replace'))
        events.append(dict(command=value, elapsed_seconds=time.monotonic()-started))
        process.stdin.write((value+'\r\n').encode('utf-8'))
        process.stdin.flush()
        marker = 'Restored checkpoint (' if value.startswith('/rewind') else 'Completed in '
        return wait_prompt(offset, marker)

    try:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        config = dict(system_prompt='Fixed local integration fixture.', request_timeout_seconds=20,
                      proxy=dict(enabled=False), providers=[dict(name='Fixture', protocol='openai-compat',
                      base_url=f'http://127.0.0.1:{server.server_port}/v1', api_key_env='STARCODE_FIXTURE_KEY',
                      model='fixture', thinking=False, context_window=128000)])
        save(work / 'config.yaml', config)  # JSON is accepted by the production YAML loader.
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('STAR_CODE_', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')):
                env.pop(key)
        env.update(STARCODE_FIXTURE_KEY='local-fixture-no-secret', STAR_CODE_SANDBOX='off',
                   HOME=str(home), USERPROFILE=str(home))
        args = ['java', '-Dfile.encoding=UTF-8', '-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8', '-Duser.home='+str(home),
                '-Dorg.jline.terminal.dumb=true', '-jar', str(jar), str(work / 'config.yaml')]
        process = subprocess.Popen(args, cwd=work, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        def drain():
            while True:
                chunk = process.stdout.read(1)
                if not chunk:
                    break
                terminal.extend(chunk)
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        wait_prompt(0)
        command('EDIT_FIXTURE')
        require(len(requests) == 2, 'Expected one tool round and one completion')
        require((work/'existing.txt').read_text() == 'after' and (work/'created.txt').read_text() == 'created', 'Production file tools did not apply both changes')
        record['checks'].append('CLI -> AgentLoop -> HTTP SSE -> both production file tools -> tool result HTTP round trip')
        text = command('/rewind 1 conversation')
        require('Restored checkpoint (conversation)' in text, 'Conversation rewind was not acknowledged')
        require((work/'existing.txt').read_text() == 'after' and (work/'created.txt').exists(), 'Conversation-only rewind modified files')
        record['checks'].append('Conversation-only rewind preserves changed files')
        text = command('/rewind 1 files')
        require('Restored checkpoint (files)' in text, 'File rewind was not acknowledged')
        require((work/'existing.txt').read_text() == 'before' and not (work/'created.txt').exists(), 'File rewind did not restore original state')
        record['checks'].append('File rewind restores edited content and removes newly created file')
        command('VERIFY_CONTEXT')
        require(len(requests) == 3 and not errors, 'Unexpected call count or fixture assertion')
        record['checks'].append('Next serialized model request excludes rewound conversation')
        text = command('/rewind 1 both')
        require('Restored checkpoint (both)' in text, 'Combined rewind was not acknowledged')
        require((work/'existing.txt').read_text() == 'before' and not (work/'created.txt').exists(), 'Repeated combined rewind changed restored files')
        record['checks'].append('Combined rewind remains available after separate rewind operations')
        journals = list(work.glob('.mewcode/sessions/*/file-history.json'))
        require(len(journals) == 1, 'Expected one persisted checkpoint journal')
        save(OUT / 'final-file-history.json', json.loads(journals[0].read_text()))
        process.stdin.write(b'/exit\r\n')
        process.stdin.flush()
        process.wait(timeout=15)
        reader.join(timeout=2)
        require(process.returncode == 0 and not errors, 'CLI did not exit cleanly')
        record['status'] = 'PASS'
    except Exception as error:
        record['exception'] = type(error).__name__+': '+str(error)
        if 'AccessDeniedException' in bytes(terminal).decode('utf-8', errors='replace'):
            record['status'] = 'BLOCKED'
            record['blocker'] = 'Java filesystem access denied before application validation completed'
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if server is not None:
            server.shutdown()
            server.server_close()
        (OUT/'terminal.log').write_bytes(bytes(terminal))
        save(OUT/'commands.json', events)
        record.update(wall_clock_seconds=time.monotonic()-started, http_calls=len(requests), fixture_errors=errors)
        save(OUT/'result.json', record)
        print('STATUS='+record['status'])
        print('RESULTS='+str(OUT))
        if 'exception' in record:
            print(record['exception'])
    return 0 if record['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
