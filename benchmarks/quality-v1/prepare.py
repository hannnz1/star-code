"""Freeze two independent checkouts. No production working-tree writes or secrets copied."""
import hashlib,json,random,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; PROJECT=ROOT.parent
BASE='014808a0b0942f25bc4f1c3f415fa63262f98176'
WORK=ROOT/'.work/quality-v1';WORK.mkdir(parents=True,exist_ok=True)
def git(p,*args):
    return subprocess.check_output(['git','-c','safe.directory='+p.as_posix(),'-c','core.hooksPath=NUL','-C',str(p),*args],stderr=subprocess.STDOUT,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def main():
    manifest_path=ROOT/'quality-v1/freeze.json'
    if manifest_path.exists():raise SystemExit('Already frozen; do not overwrite an existing study.')
    assert git(PROJECT,'rev-parse','benchmark-baseline-v1^{commit}')==BASE
    changes=git(PROJECT,'diff','--name-only',BASE,'--','src/main').splitlines()
    assert changes==['src/main/java/com/starcode/context/ContextManager.java'],changes
    manifest={'baseline':BASE,'runs_per_arm':20,'seed':20260905,'production_changes':changes,'arms':{}}
    for arm in ['old','new']:
        dest=WORK/arm
        subprocess.run(['git','-c','safe.directory='+PROJECT.as_posix(),'clone','--no-hardlinks','--no-checkout',str(PROJECT),str(dest)],check=True,capture_output=True)
        git(dest,'checkout','--detach',BASE)
        if arm=='new':
            for name in ['src/main/java/com/starcode/context/ContextManager.java','src/main/java/com/starcode/context/SummaryValidator.java','src/test/java/com/starcode/context/ContextManagerTest.java','src/test/java/com/starcode/context/CompressionReliabilityTest.java']:
                shutil.copy2(PROJECT/name,dest/name)
                git(dest,'add','--',name)
            git(dest,'-c','user.name=Benchmark Snapshot','-c','user.email=benchmark@localhost','commit','-m','Freeze current context reliability implementation for quality study')
        assert git(dest,'status','--porcelain')==''
        files={p.relative_to(dest).as_posix():sha(p) for p in sorted((dest/'src').rglob('*')) if p.is_file()}
        manifest['arms'][arm]={'checkout':str(dest),'commit':git(dest,'rev-parse','HEAD'),'source_hashes':files}
        # Save prompts directly from the frozen source; no reconstruction by the harness.
        code=(dest/'src/main/java/com/starcode/context/ContextManager.java').read_text(encoding='utf-8')
        (ROOT/f'quality-v1/{arm}-ContextManager.java.txt').write_text(code,encoding='utf-8')
    manifest['fixture_hashes']={name:sha(ROOT/name) for name in ['context-retention/conversation.json','context-retention/facts.json','context-retention/questions.json','generate_fixtures.py','report.py','reliability-v1/evaluate.py']}
    manifest['dependency_jar']=str(PROJECT/'build/libs/star-code.jar');manifest['dependency_sha256']=sha(Path(manifest['dependency_jar']))
    rng=random.Random(manifest['seed']);schedule=[]
    for pair in range(1,21):
        arms=['old','new'];rng.shuffle(arms)
        for arm in arms:schedule.append({'pair':pair,'arm':arm,'run_id':f'{arm}-{pair:02d}'})
    manifest['schedule']=schedule
    write(manifest_path,manifest)
    print(json.dumps({a:v['commit'] for a,v in manifest['arms'].items()}))
if __name__=='__main__':main()
