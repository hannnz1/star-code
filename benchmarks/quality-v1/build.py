import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    m=json.loads((ROOT/'quality-v1/freeze.json').read_text());jar=Path(m['dependency_jar'])
    assert sha(jar)==m['dependency_sha256']
    # Identical instrumentation in both arms; throttle cumulative forensic disk writes
    # to once/second and always write final data. Does not alter forwarded stream.
    source=(ROOT/'src/bench/WireRecorder.java').read_text()
    source=source.replace('WireRecorder','QualityWireRecorder').replace('long start=System.nanoTime();','long start=System.nanoTime();long lastSave=start;')
    source=source.replace('out.flush();Common.text(dir.resolve(id+"-response.sse"),redact(captured.toString(StandardCharsets.UTF_8)));','out.flush();if(System.nanoTime()-lastSave>1_000_000_000L){Common.text(dir.resolve(id+"-response.sse"),redact(captured.toString(StandardCharsets.UTF_8)));lastSave=System.nanoTime();}')
    target=ROOT/'quality-v1/QualityWireRecorder.java';target.write_text(source,encoding='utf-8')
    harness=[ROOT/'quality-v1/ABRun.java',target]+[ROOT/f'src/bench/{x}.java' for x in ['Common','RecordingClient']]
    for arm in ['old','new']:
        checkout=Path(m['arms'][arm]['checkout']);classes=ROOT/f'.work/quality-v1/classes-{arm}';classes.mkdir(exist_ok=True)
        sources=sorted((checkout/'src/main/java').rglob('*.java'))+harness
        args=ROOT/f'.work/quality-v1/{arm}-javac.args'
        options=['--release','21','-encoding','UTF-8','-cp',str(jar),'-d',str(classes)]+[str(p) for p in sources]
        args.write_text('\n'.join('"'+s.replace('\\','/')+'"' for s in options),encoding='utf-8')
        result=subprocess.run(['javac','@'+str(args)],capture_output=True,text=True)
        log=ROOT/f'results/quality-{arm}-compile.log';log.write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise SystemExit(f'{arm} compile failed; inspect {log}')
        shutil.copytree(checkout/'src/main/resources',classes,dirs_exist_ok=True)
        m['arms'][arm]['classes']=str(classes)
        m['arms'][arm]['build_sources']={str(p):sha(p) for p in sources}
        m['arms'][arm]['class_hashes']={p.relative_to(classes).as_posix():sha(p) for p in classes.rglob('*.class')}
        print(arm+' COMPILE_PASS')
    (ROOT/'quality-v1/build.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    p=subprocess.run(['java','-Dbench.root='+str(ROOT),'-cp',m['arms']['new']['classes']+';'+str(jar),'bench.ABRun',str(ROOT/'quality-v1/model-config.json'),'preflight','none'],capture_output=True,text=True)
    if p.returncode:raise SystemExit('Preflight failed: '+p.stderr[-1500:])
    print(p.stdout.strip())
if __name__=='__main__':main()
