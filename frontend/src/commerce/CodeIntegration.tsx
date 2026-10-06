import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CodeIntegrationReview, CommerceCodeHead, CommercePlan} from '../api.generated';
import type {Api} from './api';

const reasons: Record<string, string> = {ready: '可整合到项目代码基线', conflicts: '文件存在冲突，需要开发角色处理',
  no_changes: '当前基线已包含这些代码', plan_ineligible: '当前计划状态不允许整合', dismissed: '本地代码成果已放弃，原封存仍保留'};

export function CodeIntegration({api, plan}: {api: Api; plan: CommercePlan}) {
  const [review, setReview] = useState<CodeIntegrationReview | null>(null);
  const [head, setHead] = useState<CommerceCodeHead | null>(null);
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0), pending = useRef<{digest: string; id: string} | null>(null);
  const path = `/commerce/projects/${plan.project_id}/plans/${plan.id}/code-integration`;
  useEffect(() => {
    generation.current++; setReview(null); setHead(null); setConfirmed(false); setError(''); setBusy(false); pending.current = null;
    return () => {generation.current++;};
  }, [path, plan.revision]);
  async function load() {
    if (busy) return;
    const version = generation.current;
    setBusy(true); setError(''); setConfirmed(false);
    try {const value = await api<CodeIntegrationReview>(`${path}?revision=${plan.revision}`);
      if (version === generation.current) {setReview(value); setHead(null);}}
    catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '代码整合审查不可用');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function apply() {
    if (busy || !review?.applicable || !confirmed || head) return;
    const version = generation.current;
    if (pending.current?.digest !== review.review_digest) pending.current = {digest: review.review_digest, id: crypto.randomUUID()};
    setBusy(true); setError('');
    try {
      const value = await api<CommerceCodeHead>(path, {method: 'POST', body: JSON.stringify({
        expected_plan_revision: review.plan_revision, expected_head_revision: review.head_revision,
        review_digest: review.review_digest, client_request_id: pending.current.id})});
      if (version === generation.current) {setHead(value); setConfirmed(false);}
    } catch (e) {if (version === generation.current) {setError(e instanceof Error ? e.message : '整合结果未确认，请重新审查'); setConfirmed(false);}}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function decide(dismissed: boolean) {
    if (!review || busy || !window.confirm(dismissed ? ui("放弃应用这份本地代码成果？原封存和商家流程会保留。") : ui("恢复这份成果供重新审查？不会自动应用或发布。"))) return;
    const version = generation.current;
    setBusy(true); setError('');
    try {
      await api(path.replace('/code-integration', '/code-disposition'), {method: 'POST', body: JSON.stringify({
        expected_plan_revision: review.plan_revision, expected_head_revision: review.head_revision,
        review_digest: review.review_digest, client_request_id: crypto.randomUUID(), dismissed})});
      const value = await api<CodeIntegrationReview>(`${path}?revision=${plan.revision}`);
      if (version === generation.current) {setReview(value); setConfirmed(false);}
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '成果状态未确认，请重新审查');}
    finally {if (version === generation.current) setBusy(false);}
  }
  if (!plan.code_revision) return null;
  return <section className="commerce-code-integration" data-testid="code-integration">
    <h4>{ui("项目代码整合")}</h4><p>{ui("审查本计划相对代码起点的修改，整合后供后续任务使用。店铺发布需另行验证和批准。")}</p>
    <button disabled={busy} onClick={() => void load()}>{ui("审查代码整合")}</button>
    {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {head ? <p role="status">{ui("已整合到代码基线版本 ")}{head.revision} · {head.code_revision.slice(0, 10)}{ui("。后续新任务会沿用这份代码。")}</p> : review && <>
      <p role="status">{ui(reasons[review.reason] || review.reason)}{ui(" · 当前代码基线版本 ")}{review.head_revision}</p>
      <p>{ui("本计划修改文件：")}{review.changed_files.join('、') || ui("无")}</p>
      {['ready', 'conflicts'].includes(review.reason) && <button disabled={busy} onClick={() => void decide(true)}>{ui("放弃应用这份代码")}</button>}
      {review.reason === 'dismissed' && <button disabled={busy} onClick={() => void decide(false)}>{ui("恢复代码成果供审查")}</button>}
      {!!review.conflict_files.length && <p className="error">{ui("冲突文件：")}{review.conflict_files.join('、')}{ui("。保留两份原成果；请新建开发任务，在当前基线上处理冲突后重新封存。")}</p>}
      <details><summary>{ui("查看拟整合的代码差异")}</summary><pre>{review.diff || ui("没有可显示的差异。")}</pre></details>
      {review.applicable && <><label className="commerce-integration-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/>{ui("已审查代码差异，同意更新项目代码基线")}</label><button disabled={busy || !confirmed} onClick={() => void apply()}>{ui("整合到项目代码基线")}</button></>}
    </>}
  </section>;
}
