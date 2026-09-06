"""Offline secondary evaluator. Never calls a model or changes frozen legacy scoring.

Rule semantics is a conservative lexical proposition check, NOT a general semantic
judge. Rules derive only from dataset statements; synonyms are deliberately limited.
Missing matches mean unverified, not proven information loss. Every hit saves evidence.
"""
import collections, hashlib, importlib.util, json, re, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('legacy', ROOT/'report.py')
legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
read = legacy.read
STOP = set('the a an its is are was were be been being to of in on at as for by with and or this that must should use uses keep during while fixing before current exactly'.split())
# Normalization is fixed and shared by original propositions and candidate evidence.
REWRITES = [(r'\bdid not (?:fix|prevent)\b', ' failed '),
            (r'\bwithout success\b', ' failed '), (r'\bunsuccessful\b', ' failed '),
            (r'\b(?:attempted|tried)\b', ' attempted '),
            (r'\b(?:do not|must not|never|forbidden to|prohibited to)\b', ' prohibited '),
            (r'\b(?:caused by|due to)\b', ' cause '),
            (r'\b(?:milliseconds|ms)\b', ' milliseconds ')]
def tokens(s):
    s=s.casefold().replace('`','')
    for pattern,replacement in REWRITES: s=re.sub(pattern,replacement,s)
    return [t for t in re.findall(r'[a-z0-9_]+(?:[-/.][a-z0-9_]+)*',s) if t not in STOP]
def clauses(source):
    # Do not split paths, decimal numbers or commands at embedded periods.
    return [s.strip() for s in re.split(r'\n|;|(?<=[.!?])\s+',source) if s.strip()]
def exact(f, source):
    target=' '.join(f['statement'].split())
    return next((c for c in clauses(source) if target in ' '.join(c.split())),None)
def semantic(f, source):
    required=collections.Counter(tokens(f['statement']))
    # Extra negation reverses meaning even if all affirmative tokens are present.
    polarity={'not','no','never','failed','prohibited'}
    numeric=set(re.findall(r'(?<![\w])\d+(?![\w])',f['statement']))
    for c in clauses(source):
        if len(c)>1500: continue
        got=collections.Counter(tokens(c))
        if required-got: continue
        if (set(got)&polarity)!=(set(required)&polarity): continue
        # Reject competing numbers rather than choosing a convenient value.
        if numeric and set(re.findall(r'(?<![\w])\d+(?![\w])',c))!=numeric: continue
        # Multiple independently named owners are ambiguous in a single clause.
        own_index=int(f['id'][1:])-1
        other=[i for i,owners in enumerate(legacy.OWNERS) if i!=own_index and any(o.casefold() in c.casefold() for o in owners)]
        if other: continue
        return c
    return None
def stats(values):
    v=[x for x in values if x is not None]
    return dict(n=len(v),mean=statistics.mean(v),median=statistics.median(v),min=min(v),max=max(v)) if v else None
def evaluate(batch, label, facts):
    runs=[]; details=[]
    for p in sorted(batch.glob('repeat-*/run.json'),key=lambda p:int(p.parent.name.split('-')[1])):
        r=read(p); d=p.parent
        sources={k:(d/fn).read_text(encoding='utf-8') if (d/fn).exists() else '' for k,fn in [('summary','summary.txt'),('recovery attachment','recovery.txt')]}
        sources['retained recent messages']='\n\n'.join(m.get('content') or '' for m in read(d/'retained-recent.json')) if (d/'retained-recent.json').exists() else ''
        complete='\n\n'.join(m.get('content') or '' for m in read(d/'compacted-context.json')) if (d/'compacted-context.json').exists() else ''
        answers={v:read(d/f'{v}-answers.json') if (d/f'{v}-answers.json').exists() else {} for v in ['summary-only','complete-context']}
        valid=r.get('status')=='SUCCESS'; rows=[]
        for i,f in enumerate(facts):
            s,why,_=legacy.score(f,answers['summary-only'].get(f['id']),sources['summary'],legacy.OWNERS[i])
            c,_,_=legacy.score(f,answers['complete-context'].get(f['id']),complete,legacy.OWNERS[i])
            retained=any(legacy.norm(f['statement']) in [legacy.norm(line) for line in sources[k].splitlines()] for k in ['retained recent messages','recovery attachment'])
            ex={k:exact(f,v) for k,v in sources.items()}; sem={k:semantic(f,v) for k,v in sources.items()}
            row=dict(batch=label,run=d.name,id=f['id'],statement=f['statement'],legacy_summary=s,legacy_summary_reason=why,legacy_complete=c or s or retained,summary_exact=bool(ex['summary']),complete_exact=any(ex.values()),summary_semantic=bool(sem['summary']),complete_semantic=any(sem.values()),exact_evidence=ex,semantic_evidence=sem,semantic_sources=[k for k,v in sem.items() if v] or ['missing/unverified'])
            rows.append(row);details.append(row)
        out=dict(batch=label,run=d.name,status=r['status'],compact_status=r.get('compact_status',r['status']),raw_path=str(d.relative_to(ROOT)),wall_clock_seconds=r.get('wall_clock_seconds'),compact_wall_clock_seconds=r.get('compact_wall_clock_seconds'),estimated_after_tokens=r.get('estimated_after_tokens'),should_auto_compact=r.get('should_auto_compact'))
        diag=read(d/'compression-diagnostics.json') if (d/'compression-diagnostics.json').exists() else None
        calls=[read(x) for x in (d/'calls').glob('*.json')];compact=[x for x in calls if x.get('phase')=='compact']
        out.update(retries=diag['retryCount'] if diag else max(0,len(compact)-1),model_calls=len(calls),**legacy.actual_usage(d))
        # Provider usage is unavailable for interrupted/unterminated responses, never zero-fill it.
        for field in ['input_tokens','output_tokens','total_tokens']:
            vals=[x.get(field) for x in compact]
            out['compact_'+field]=sum(vals) if vals and all(isinstance(v,(int,float)) and v>0 for v in vals) else None
        for field in ['legacy_summary','legacy_complete','summary_exact','complete_exact','summary_semantic','complete_semantic']:
            out[field+'_percent']=sum(x[field] for x in rows)*100/len(facts) if valid else None
        runs.append(out)
    ok=[r for r in runs if r['compact_status']=='SUCCESS']
    summary=dict(attempts=len(runs),successful=len(ok),failed=len(runs)-len(ok),success_percent=100*len(ok)/len(runs),retry_percent=100*sum(r['retries']>0 for r in runs)/len(runs),average_retries=statistics.mean(r['retries'] for r in runs))
    for field in ['legacy_summary_percent','legacy_complete_percent','summary_exact_percent','complete_exact_percent','summary_semantic_percent','complete_semantic_percent','wall_clock_seconds','compact_wall_clock_seconds','compact_input_tokens','compact_output_tokens','compact_total_tokens','input_tokens','output_tokens','total_tokens']:
        summary[field]=stats(r.get(field) for r in (ok if field not in ['wall_clock_seconds'] else runs))
    return dict(summary=summary,runs=runs,facts=details)
def selftest(facts):
    count=0
    for f in facts:
        assert exact(f,f['statement']),f['id']
        assert semantic(f,f['statement']),f['id']
        assert not semantic(f,'UnrelatedWidget has no pending work.'),f['id']
        if 'prohibited' not in tokens(f['statement']) and 'failed' not in tokens(f['statement']):
            assert not semantic(f,'Not true: '+f['statement']),f['id']
        else:
            wrong=f['statement'].replace('Do not','Do').replace('must not','must').replace('did not fix','fixed').replace('did not prevent','prevented').replace('without success','successfully').replace('failed','succeeded')
            assert not semantic(f,wrong),f['id']
        count+=4
    f=facts[3]
    assert not semantic(f,f['statement'].replace('730','731'))
    assert not semantic(f,f['statement'].replace('RetryQueue','OtherQueue'))
    assert not semantic(f,f['statement'].rstrip('.')+' and SearchBackfill must wait 730 milliseconds.')
    return count+3
def main():
    manifest=read(ROOT/'reliability-v1/comparison-manifest.json')
    for path,expected in manifest['files'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,'Frozen file changed: '+path
    facts=read(ROOT/'context-retention/facts.json')['facts']; tests=selftest(facts)
    before=ROOT/manifest['before_batch']; after=ROOT/(ROOT/'results/context-reliability-latest.txt').read_text().strip()
    result=dict(evaluator_version='conservative-proposition-v1',evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),selftest_assertions=tests,limitations=['Secondary rule evaluator was created after generation; not a preregistered semantic endpoint.','Rule semantic scores require lexical proposition coverage and are not a validated general semantic judge. Unmatched paraphrases are unverified.','Exact means complete original sentence, case-sensitive with whitespace normalization.','Legacy extraction/scorer remain frozen; successful runs only enter retention statistics.'],before=evaluate(before,'before',facts),after=evaluate(after,'after',facts))
    dest=ROOT/'results/summary/context-reliability-comparison.json';legacy.write(dest,result)
    for k in ['before','after']:print(k,json.dumps(result[k]['summary']))
    print('SELFTEST_ASSERTIONS='+str(tests));print('REPORT_DATA='+str(dest))
if __name__=='__main__': main()
