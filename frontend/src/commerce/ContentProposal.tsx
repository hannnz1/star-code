import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {ContentConfirmation, ContentProposal as Proposal, StoreProject} from '../api.generated';
import type {Api} from './api';

export function ContentProposal({api, projectId, planId, onConfirmed}: {
  api: Api; projectId: string; planId: string; onConfirmed: (project: StoreProject) => void;
}) {
  const [view, setView] = useState<Proposal | null>(null), [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const active = useRef(true);
  useEffect(() => {active.current = true; return () => {active.current = false;};}, []);
  const path = `/commerce/projects/${projectId}/plans/${planId}/content-proposal`;
  async function read() {
    if (busy) return;
    setBusy(true); setError(''); setChecked(false);
    try {
      const value = await api<Proposal>(path);
      if (active.current) setView(value);
    } catch (e) {if (active.current) {setView(null); setError(e instanceof Error ? e.message : '候选读取未完成');}}
    finally {if (active.current) setBusy(false);}
  }
  async function confirm() {
    if (busy || !checked || !view || view.status !== 'PENDING') return;
    setBusy(true); setError('');
    try {
      const value = await api<ContentConfirmation>(`${path}/${view.id}/confirm`, {method: 'POST', body: JSON.stringify({
        expected_project_revision: view.project_revision, expected_plan_revision: view.plan_revision, content_digest: view.content_digest,
      })});
      if (active.current) onConfirmed(value.project);
    } catch (e) {if (active.current) {setChecked(false); setError(e instanceof Error ? e.message : '文案确认未完成');}}
    finally {if (active.current) setBusy(false);}
  }
  return <section className="commerce-content-proposal">
    <button disabled={busy} onClick={() => void read()}>{ui("查看商品文案候选")}</button>
    {error && <p className="error commerce-error" role="alert">{uiFeedback(error)}</p>}
    {view && <>
      <h4>{ui("商家文案确认")}</h4><p>{ui("逐项核对标题与描述。确认后生成新资料批次，旧计划停止，需重新准备代码、验证和批准发布。")}</p>
      <p>{ui("候选摘要：")}<code>{view.content_digest}</code></p>
      {view.original.map((original, index) => <article key={original.sku} className="commerce-import">
        <h4>SKU：{original.sku}</h4><p>{ui("价格")}{original.price} {original.currency}{ui(" · 库存 ")}{original.stock}{ui(" · 分类 ")}{original.category || ui("未指定")}</p>
        <p><strong>{ui("原始标题：")}</strong>{original.title}</p><p><strong>{ui("建议标题：")}</strong>{view.candidates[index].title}</p>
        <p><strong>{ui("原始描述：")}</strong>{original.description || ui("空")}</p><p><strong>{ui("建议描述：")}</strong>{view.candidates[index].description || ui("空")}</p>
      </article>)}
      {view.status === 'PENDING' ? <>
        <label><input type="checkbox" checked={checked} disabled={busy} onChange={e => setChecked(e.target.checked)}/>{ui("我已核对改写文案中的商品事实")}</label>
        <button disabled={busy || !checked} onClick={() => void confirm()}>{ui("确认文案并生成新资料批次")}</button>
      </> : <p>{ui("这份文案已确认。请使用新批次重新创建团队任务。")}</p>}
    </>}
  </section>;
}
