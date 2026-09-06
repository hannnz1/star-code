"""Offline MCP summary from captured production requests. No model calls."""
import json,csv,sys,os,statistics,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=ROOT/'results'
sys.path.insert(0,str(ROOT/'.work/python'));os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(ROOT/'.work/tiktoken'))
import tiktoken
ENC=tiktoken.get_encoding('o200k_base')
METHOD='estimated: tiktoken0.12.0/o200k_base; compact JSON arrays; not provider-official schema tokens'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def tokens(v):return len(ENC.encode(encoded(v),disallowed_special=()))
def mean(rows,key):
 values=[r[key] for r in rows if r.get(key) is not None]
 return statistics.mean(values) if values else None
def median(rows,key):
 values=[r[key] for r in rows if r.get(key) is not None]
 return statistics.median(values) if values else None
def latest(kind):
 p=OUT/(kind+'-latest.txt')
 if p.exists():return ROOT/p.read_text().strip()
 dirs=sorted((OUT/'raw'/kind).glob('*'));return dirs[-1] if dirs else None
def records(batch):
 result=[]
 if batch is None:return result
 for path in sorted(batch.glob('*/run.json')):
  r=read(path);requests=[read(p) for p in sorted(path.parent.glob('wire/*-request.json'))]
  if not requests:result.append(dict(r,raw_directory=path.parent.relative_to(ROOT).as_posix()));continue
  arrays=[q.get('tools',[]) for q in requests]
  external=[[d for d in a if d['name'].startswith('mcp__') or d['name']=='search_mcp_tools'] for a in arrays]
  union={d['name']:d for a in arrays for d in a if d['name'].startswith('mcp__')}
  usages=[]
  for file in sorted(path.parent.glob('wire/*-response.sse')):
   for line in file.read_text(encoding='utf-8').splitlines():
    if not line.startswith('data:'):continue
    try:e=json.loads(line[5:])
    except json.JSONDecodeError:continue
    if e.get('type')=='response.completed' and e.get('response',{}).get('usage'):usages.append(e['response']['usage'])
  row=dict(r,raw_directory=path.parent.relative_to(ROOT).as_posix(),model_calls=len(requests),
   initial_schema_bytes=len(encoded(external[0]).encode()),initial_schema_tokens_estimated=tokens(external[0]),
   initial_all_tools_tokens_estimated=tokens(arrays[0]),complete_initial_request_tokens_estimated=tokens(requests[0]),
   total_schema_tokens_estimated=sum(tokens(a) for a in external),
   total_all_tools_tokens_estimated=sum(tokens(a) for a in arrays),
   loaded_unique_schema_tokens_estimated=tokens(list(union.values())) if union else 0,
   tokenizer_method=METHOD,usage_records=len(usages),usage_complete=len(usages)==len(requests))
  for key in ['input_tokens','output_tokens','total_tokens']:
   row['known_'+key]=sum(u.get(key,0) for u in usages)
   row[key]=row['known_'+key] if len(usages)==len(requests) else None
  result.append(row)
 return result
def writecsv(path,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
def main():
 schema=records(latest('mcp-schema-v1'));selection=records(latest('mcp-selection-v1'))
 assert len(schema)==40 and all(r['status']=='SUCCESS' for r in schema)
 groups=[]
 for count in [10,25,50,100]:
  full=[r for r in schema if r['tool_count']==count and r['loading_mode']=='FULL']
  lazy=[r for r in schema if r['tool_count']==count and r['loading_mode']=='LAZY']
  assert len(full)==len(lazy)==5
  f=mean(full,'initial_schema_tokens_estimated');l=mean(lazy,'initial_schema_tokens_estimated')
  groups.append({'tool_count':count,'runs_per_mode':5,'full_initial_tokens_estimated':f,'lazy_initial_tokens_estimated':l,
   'initial_schema_reduction':1-l/f,'full_schema_bytes':mean(full,'initial_schema_bytes'),'lazy_schema_bytes':mean(lazy,'initial_schema_bytes'),
   'full_token_sample_sd':statistics.stdev(r['initial_schema_tokens_estimated'] for r in full),
   'lazy_token_sample_sd':statistics.stdev(r['initial_schema_tokens_estimated'] for r in lazy)})
 modes={}
 for mode in ['FULL','LAZY']:
  rs=[r for r in selection if r['loading_mode']==mode]
  modes[mode]={'runs':len(rs),'task_success':sum(r.get('task_success') is True for r in rs),
   'selection_correct':sum(r.get('selection_correct') is True for r in rs),
   'execution_failures':sum(r['status']!='SUCCESS' for r in rs),
   **{'median_'+key:median(rs,key) for key in ['agent_wall_clock_seconds','model_calls','total_tokens','initial_schema_tokens_estimated','total_schema_tokens_estimated','loaded_unique_schema_tokens_estimated']},
   'known_total_tokens':sum(r.get('known_total_tokens',0) for r in rs),'usage_complete_runs':sum(r.get('usage_complete',False) for r in rs)}
 pairs=[]
 for task in read(HERE/'selection-fixture.json')['tasks']:
  candidates={r['loading_mode']:r for r in selection if r['run_id'].startswith(task['id']+'-')}
  if set(candidates)!={'FULL','LAZY'}:continue
  f,l=candidates['FULL'],candidates['LAZY']
  pairs.append({'task':task['id'],'full_success':f['task_success'],'lazy_success':l['task_success'],
   'initial_schema_reduction':1-l['initial_schema_tokens_estimated']/f['initial_schema_tokens_estimated'],
   'total_schema_reduction':1-l['total_schema_tokens_estimated']/f['total_schema_tokens_estimated'],
   'extra_model_calls':l['model_calls']-f['model_calls'],
   'latency_difference_seconds':l['agent_wall_clock_seconds']-f['agent_wall_clock_seconds']})
 result={'schema_groups':groups,'selection':modes,'pairs':pairs,'estimation_method':METHOD,
  'selection_complete':len(selection)==20 and len(pairs)==10,
  'schema_batch':str(latest('mcp-schema-v1')),'selection_batch':str(latest('mcp-selection-v1')),
  'production_status':'IMPLEMENTED_NEEDS_MORE_TESTING'}
 if result['selection_complete'] and all(v['task_success']==10 for v in modes.values()):
  result['production_status']='IMPLEMENTED_AND_VERIFIED'
 (OUT/'mcp-lazy-loading-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 writecsv(OUT/'mcp-lazy-schema-runs.csv',schema)
 if selection:writecsv(OUT/'mcp-lazy-selection-runs.csv',selection)
 lines=['# MCP Lazy Loading final validation','',f"**{result['production_status']}** (scope: fixed synthetic fixtures; not general noninferiority).",'',
  '## Production implementation','',
  'Commit64e4c92f5b623a166879ee5aa86f23fd09d50867. Tool.deferred marks MCP adapters; ModelToolCatalog builds the allowed short index, searches/activates schemas; AgentLoop refreshes each request and owns activation state. Permissions and hooks remain on execution. STAR_CODE_MCP_LOADING=full restores full exposure. MCP tools/list still downloads schemas upfront; only model-facing exposure is lazy.',
  '', '## Initial schema overhead','',METHOD+'. Includes MCP schemas or discovery schema/index, excludes the six common builtins. All-tools and complete-request estimates are separately in CSV.',
  '', '| MCP tools | FULL estimate | LAZY estimate | Initial reduction | Repeats/mode |','|---|---:|---:|---:|---:|']
 for g in groups:lines.append(f"| {g['tool_count']} | {g['full_initial_tokens_estimated']:.0f} | {g['lazy_initial_tokens_estimated']:.0f} | {100*g['initial_schema_reduction']:.2f}% | 5 |")
 lines+=['','Token SD=0 for identical deterministic fixture/request schema content; five repeats test the serialization path, not independent statistical evidence about models. Schemas are synthetic copies of six production builtin definitions, not representative of real MCP marketplace schema sizes. The valid pre-change full baseline is separately preserved under results/raw/mcp-full-current/2026-09-06T07-32-04.514852900Z.',
  '', '## Real model tool selection','',
  'Ten fixed service questions,100 synthetic tools including90 distractors; both modes use identical prompts/config and independently fresh Agents, pair order seeded20260905. True local MCP server validates actual selected tool/entity argument, then returns a fixed answer. Final answer must include that exact value and no unexpected remote call. These are real model calls to synthetic services, not live business endpoints.',
  '', '| Mode | Task success | Correct selection | Median calls | Median Agent seconds | Median provider total tokens |','|---|---:|---:|---:|---:|---:|']
 for mode,m in modes.items():lines.append(f"| {mode} | {m['task_success']}/{m['runs']} | {m['selection_correct']}/{m['runs']} | {m['median_model_calls']} | {m['median_agent_wall_clock_seconds']} | {m['median_total_tokens']} |")
 if pairs:
  lines+=['',f"Paired mean extra model calls: {mean(pairs,'extra_model_calls'):.2f}; paired median latency difference LAZY−FULL: {median(pairs,'latency_difference_seconds'):.2f}s.",
   f"Paired median total-schema reduction (sum of MCP/index tool-array estimates over all requests): {100*median(pairs,'total_schema_reduction'):.2f}%. This differs from both initial reduction and whole-task provider token usage."]
 lines+=['','Unique activated schema size, cumulative schema token cost, model calls, usage coverage, errors and raw paths are in the per-run CSV. Schema-only runs have no actual loading or task and must not be used for cumulative task-cost savings.',
  '', '## Validation and limitations','',
  '- Full Gradle test passed195 tests across53 suites,0 failures/errors/skips; logs mcp-lazy-full-tests.txt/json. Unit tests cover activation, session isolation, mode filtering, malformed search and actual permission denial. The benchmark exercises real stdio SDK discovery/call and actual model HTTP serialization.',
  '- No model sampling seed was set; fixture/order seed is not a model seed. Same model/config fields do not guarantee a fixed backend snapshot.',
  '- Simple single-operation tasks, one run per task/mode. Even10/10 does not establish statistical noninferiority, robustness to malicious tool metadata or broad third-party coverage.',
  '- Search is lexical, bounded to5 matches; a short index still grows linearly. Loaded schemas persist for the Agent lifetime, no eviction. Restart loses activation and requires rediscovery.',
  '- Both model protocols share the catalog path; this real-model benchmark exercises Responses only. No Anthropic E2E result is implied.',
  '- Raw failures are retained. Reported task success requires correctness, not just Agent completion. Null usage is not zero cost. No85% target or whole-task-token-saving claim.',
  '', '## Reproduce','',
  'Run current benchmarks/run.ps1 compile using PowerShell7 (old Windows PowerShell may promote javac notes to errors); classpath is .work/classes-<first12 build-manifest SHA>; invoke bench.McpLazyBench schema or selection with -Dbench.root and -Dbench.harness.sha. selection makes paid model calls. Offline regenerate: python benchmarks/mcp-lazy-v1/summarize.py (bundled .work/python tiktoken dependency required). Preserve raw batch directories, build manifests and fixture files together.',
  '', '## Resume wording','',
  'Describe the measured initial schema reduction only with the100-tool synthetic-fixture scope and tool-selection sample size. Do not substitute85%, generalize ten tasks to universal correctness, or describe this as reducing all task tokens.']
 (OUT/'mcp-lazy-loading-final.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
