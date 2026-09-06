"""User-requested two-stage, blinded human sample. No model annotations."""
import collections,csv,hashlib,json,random
from pathlib import Path
csv.field_size_limit(10_000_000)
ROOT=Path(__file__).resolve().parents[1]
CATEGORY={'class':'identifier_class_method','method':'identifier_class_method','package':'identifier_class_method','file':'filename_path','number':'numeric_parameter','api':'api_contract','constraint':'user_constraint','negative':'user_constraint','failed_attempt':'failed_attempt','cause':'bug_root_cause','pending':'todo_current_state','next':'todo_current_state'}
def csvwrite(p,rows):
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def select_bands(cases,n,rng):
 bands=collections.defaultdict(list)
 for c in cases:bands[c['band']].append(c)
 names=sorted(bands);rng.shuffle(names)
 for xs in bands.values():rng.shuffle(xs)
 selected=[]
 while len(selected)<n:
  progress=False
  for name in names:
   if bands[name] and len(selected)<n:selected.append(bands[name].pop());progress=True
  if not progress:break
 return selected
def prepare(batch,details,facts):
 rng=random.Random(20260905);by_id={f['id']:f for f in facts}
 conversation=json.loads((ROOT/'context-retention/conversation.json').read_text())
 contexts={f['id']:next((m['content'] for m in conversation if f['statement'] in (m.get('content') or '')),f['statement']) for f in facts}
 scores=collections.defaultdict(list)
 for r in details:
  for view in ['summary','effective']:scores[(r['run_id'],view)].append(r[view+'_semantic_supported'])
 strata=collections.defaultdict(list)
 for r in details:
  for view in ['summary','effective']:
   values=scores[(r['run_id'],view)];percent=100*sum(values)/len(values)
   band='low_<50' if percent<50 else 'middle_50_80' if percent<80 else 'high_>=80'
   cat=CATEGORY[r['category']]
   strata[(r['arm'],view,cat)].append(dict(row=r,view=view,band=band,category=cat))
 pool=[];sample=[]
 # 2 arms * 2 views * 8 represented categories =32 strata; 25 ->5 each.
 for key in sorted(strata):
  candidates=select_bands(strata[key],25,rng);pool.extend(candidates)
  sample.extend(select_bands(candidates,5,rng))
 rng.shuffle(sample);blind=[];key_rows=[]
 for i,c in enumerate(sample,1):
  r=c['row'];view=c['view'];fact=by_id[r['id']];review=f'R{i:04d}'
  source=(batch/r['run_id']/'forensics'/f'{view}.txt').read_text(encoding='utf-8')
  blind.append(dict(review_id=review,fact_category=c['category'],original_fact=fact['statement'],source_context=contexts[r['id']],compressed_context_or_summary=source,human_label='',human_notes=''))
  key_rows.append(dict(review_id=review,version=r['arm'].upper(),run_id=r['run_id'],fact_id=r['id'],view=view,fact_category=c['category'],automatic_exact_result='NOT_APPLICABLE' if r[view+'_exact'] is None else 'PASS' if r[view+'_exact'] else 'NOT_VERIFIED',automatic_semantic_result=r[view+'_state'],judge_result='NOT_USED',score_band=c['band'],source_sha256=hashlib.sha256(source.encode()).hexdigest()))
 dest=ROOT/'results/manual-review-blind.csv';key_path=ROOT/'results/manual-review-key.csv'
 if dest.exists():
  with dest.open(encoding='utf-8-sig',newline='') as f:existing=list(csv.DictReader(f))
  assert [{k:v for k,v in r.items() if k not in ['human_label','human_notes']} for r in existing]==[{k:v for k,v in r.items() if k not in ['human_label','human_notes']} for r in blind],'Existing review data differs; never overwrite human work'
 else:csvwrite(dest,blind)
 if not key_path.exists():csvwrite(key_path,key_rows)
 # Candidate IDs and strata are analyst-only; they do not enter blind CSV.
 candidate_rows=[dict(run_id=c['row']['run_id'],fact_id=c['row']['id'],arm=c['row']['arm'],view=c['view'],category=c['category'],score_band=c['band']) for c in pool]
 (batch/'manual-review-candidate-pool.json').write_text(json.dumps(candidate_rows,indent=2),encoding='utf-8')
 metadata=dict(status='PENDING',total_fact_view_records=len(details)*2,candidate_pool=len(pool),human_sample=len(sample),seed=20260905,category_counts=dict(collections.Counter(c['category'] for c in sample)),arm_counts=dict(collections.Counter(c['row']['arm'] for c in sample)),view_counts=dict(collections.Counter(c['view'] for c in sample)),score_band_counts=dict(collections.Counter(c['band'] for c in sample)),absent_categories=['architectural_decision','real_tool_result'],human_disagreement_rate=None,blind_csv=str(dest),key_csv=str(key_path),sampling_note='Latest user instruction supersedes original 20% of all judgments: 800 candidates ->160 human sample, 4% of 4000 total. Equal arm/view/category allocation and score-band coverage; not an unstratified population error estimate.')
 (ROOT/'results/manual-review-sampling.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
 (ROOT/'results/manual-review-instructions.md').write_text('''# 人工盲审说明

请只打开 manual-review-blind.csv。不要在完成前打开 manual-review-key.csv、自动评分报告或采样统计中的版本/分数信息。

每行阅读 original_fact、source_context，以及完整 compressed_context_or_summary，然后填写 human_label 和 human_notes。原文和待判断文本都完整保存，没有只截取自动评分支持的片段。请注意：部分长文本可能超过 Excel 单元格长度限制；使用不会截断长文本的 CSV 工具。CSV 是标准 UTF-8 BOM、带引号的多行字段，物理行数不等于记录数。

- PASS：核心事实和含义完整保留，没有影响后续任务执行的错误。
- PARTIAL：保留主要语义，但丢失重要限定、参数或细节。
- FAIL：缺失、错误、反转、混淆，或无法从待判断文本恢复。
- UNCERTAIN：现有上下文不足以可靠判断。

请按整条事实判断主体、数值和单位、否定关系、失败/待办状态；允许正确同义改写。不要修改 review_id 或原文列。human_notes 建议写证据及具体缺失/错误。完成后运行 quality-v1/compare_manual.py；该脚本才读取独立 key。模型没有代填人工标签，当前 human audit=PENDING。

人工样本按最新要求为约800候选的20%，即160条；不是全部4000 fact/view记录的20%。不同类别和分数层有意覆盖，样本一致率不能直接当作全体无偏错误率。
''',encoding='utf-8')
 return metadata
