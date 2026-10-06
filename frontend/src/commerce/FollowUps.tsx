import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, CommerceTaskDraft, FollowUpSuggestion, ModelSuggestionJob} from '../api.generated';
import type {Api} from './api';

export function FollowUps({api, plan, onDraft, onDrafts, active = true}: {
  api: Api; plan: CommercePlan; onDraft: (draft: CommerceTaskDraft) => void; onDrafts: (drafts: CommerceTaskDraft[]) => void; active?: boolean;
}) {
  const visible = useRef(active); visible.current = active;
  const visibilityVersion = useRef(0);
  useEffect(() => {visibilityVersion.current++;}, [active]);
  const [items, setItems] = useState<FollowUpSuggestion[] | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [jobs, setJobs] = useState<ModelSuggestionJob[]>([]);
  const [selected, setSelected] = useState<string[]>([]), [notice, setNotice] = useState('');
  const [editing, setEditing] = useState(false);
  const batchPending = useRef<{key: string; id: string} | null>(null);
  const modelPending = useRef<string | null>(null);
  const generation = useRef(0), pending = useRef<{digest: string; id: string} | null>(null);
  const path = `/commerce/projects/${plan.project_id}/plans/${plan.id}/follow-ups`;
  useEffect(() => {
    generation.current++; setItems(null); setBusy(false); setError(''); pending.current = null;
    setSelected([]); setNotice(''); setEditing(false); batchPending.current = null;
    return () => {generation.current++;};
  }, [path, plan.revision]);
  const modelPath = `/commerce/projects/${plan.project_id}/plans/${plan.id}/follow-up-model-jobs`;
  useEffect(() => {
    let active = true; setJobs([]); modelPending.current = null;
    const poll = () => void api<ModelSuggestionJob[]>(modelPath).then(value => {if (active) setJobs(value);}).catch(() => {});
    poll(); const timer = window.setInterval(poll, 5000);
    return () => {active = false; window.clearInterval(timer);};
  }, [api, modelPath]);
  async function generate() {
    if (!active || busy || !window.confirm(ui("使用当前模型生成后续建议？会发送品牌名称、语言、计划状态、错误码、角色成果哈希及已封存主题差异摘要（最多 8000 字符），最多调用模型一次并消耗额度。不发送模型凭据、订单或其他项目文件，不会启动建议任务。"))) return;
    const version = generation.current;
    const visibility = visibilityVersion.current;
    setBusy(true); setError('');
    modelPending.current ||= crypto.randomUUID();
    try {
      const project = await api<{project_revision: number}>(`/commerce/projects/${plan.project_id}/task-capacity`);
      if (version !== generation.current || !visible.current || visibility !== visibilityVersion.current) return;
      const value = await api<ModelSuggestionJob>(modelPath, {method: 'POST', body: JSON.stringify({
        expected_plan_revision: plan.revision, expected_project_revision: project.project_revision, client_request_id: modelPending.current})});
      if (version === generation.current) {setJobs(previous => [...previous.filter(item => item.id !== value.id), value]); modelPending.current = null;}
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '建议任务未创建');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function load() {
    if (busy) return;
    const version = generation.current;
    setBusy(true); setError('');
    try {
      const value = await api<FollowUpSuggestion[]>(path);
      if (version === generation.current) setItems(value);
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '建议暂不可用');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function saveSelected() {
    if (busy || !selected.length) return;
    const version = generation.current;
    const chosen = items?.filter(item => selected.includes(item.id)) || [];
    const payload = {items: chosen.map(item => ({suggestion_id: item.id, review_digest: item.review_digest}))};
    const key = JSON.stringify(payload);
    if (batchPending.current?.key !== key) batchPending.current = {key, id: crypto.randomUUID()};
    setBusy(true); setError(''); setNotice('');
    try {
      const values = await api<CommerceTaskDraft[]>(path + '/accept-batch', {method: 'POST', body: JSON.stringify({...payload, client_request_id: batchPending.current.id})});
      if (version === generation.current) {onDrafts(values); setSelected([]); setNotice(`已保存 ${values.length} 份建议草稿，可在看板批量启动或取消。`); batchPending.current = null;}
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '批量保存未完成');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function accept(item: FollowUpSuggestion) {
    if (busy) return;
    const version = generation.current;
    if (pending.current?.digest !== item.review_digest) pending.current = {digest: item.review_digest, id: crypto.randomUUID()};
    setBusy(true); setError('');
    try {
      const draft = await api<CommerceTaskDraft>(path + '/accept', {method: 'POST', body: JSON.stringify({
        suggestion_id: item.id, review_digest: item.review_digest, client_request_id: pending.current.id})});
      if (version === generation.current) {if (visible.current) onDraft(draft); else onDrafts([draft]);}
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '建议已变化，请重新读取');}
    finally {if (version === generation.current) setBusy(false);}
  }
  return <section className="commerce-follow-ups" data-testid="commerce-follow-ups">
    <h4>{ui("根据成果安排下一步")}</h4>
    <p>{ui("建议由计划状态与错误证据生成。保存为草稿不会调用模型，也不会启动或发布。")}</p>
    <button disabled={busy} onClick={() => void load()}>{ui("读取后续建议")}</button>
    <button disabled={busy || jobs.some(job => job.status === 'QUEUED' || job.status === 'RUNNING')} onClick={() => void generate()}>{ui("用当前模型生成更多建议")}</button>
    {jobs.slice(-1).map(job => <p key={job.id} role="status">{ui("模型建议任务：")}{job.status}{ui(" · 请求 ")}{job.model_requests}/1{job.error_code ? ` · ${job.error_code}` : ''}{ui("。完成后读取建议，确认后保存草稿。")}</p>)}
    {items?.length === 0 && <p role="status">{ui("当前没有可用建议。先处理原任务或更新项目资料。")}</p>}
    {!!items?.length && <button onClick={() => {setEditing(value => !value); setSelected([]);}}>{ui(editing ? '完成批量管理' : '批量管理建议')}</button>}
    {!!selected.length && <><button disabled={busy} onClick={() => void saveSelected()}>{ui("保存所选建议为草稿（")}{selected.length}）</button><button disabled={busy} onClick={() => setSelected([])}>{ui("取消建议选择")}</button></>}
    {notice && <p role="status">{uiFeedback(notice)}</p>}
    {items?.map(item => <article className="commerce-import" key={item.id}>
      <h5>{item.title}</h5><p>{item.prompt}</p>
      {editing && <label><input type="checkbox" aria-label={ui("选择建议 {0}", [item.title])} checked={selected.includes(item.id)} disabled={busy}
        onChange={event => setSelected(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))}/>{ui("选择这项建议")}</label>}
      <ul>{item.evidence.map(evidence => <li key={evidence}>{evidence}</li>)}</ul>
      <p>{ui("来源计划 ")}{item.source_plan_id.slice(0, 8)}{ui(" · 版本 ")}{item.source_plan_revision}{ui(" · 代码基线 ")}{item.code_base_revision}</p>
      <button disabled={busy} onClick={() => void accept(item)}>{ui("保存建议草稿：")}{item.title}</button>
    </article>)}
    {error && <p role="alert" className="error">{uiFeedback(error)}</p>}
  </section>;
}
