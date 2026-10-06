import {ui, uiFeedback} from '../i18n';
import {useCallback, useEffect, useRef, useState} from 'react';
import type {CommercePlan, VerificationStatus} from '../api.generated';
import type {Api} from './api';

const phases = [['reference', '隔离环境'], ['source_capture', '封存来源'], ['staging', '部署预览'],
  ['buyer', '购买流程'], ['browser', '页面截图'], ['facts', '商品事实']];
const states: Record<string, string> = {QUEUED: '等待验证', RUNNING: '正在验证', COLLECTED: '正在生成审查报告',
  REVIEW_REQUIRED: '报告就绪，等待审查', NEEDS_RECONCILIATION: '结果待核对', CANCELLED: '已取消'};

export function VerificationPanel({api, plan, onPlan}: {api: Api; plan: CommercePlan; onPlan: (plan: CommercePlan) => void}) {
  const [jobs, setJobs] = useState<VerificationStatus[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const path = `/commerce/projects/${plan.project_id}/plans/${plan.id}`;
  const active = useRef(true), request = useRef<{revision: number; id: string} | null>(null);
  const refresh = useCallback(async () => {
    const values = await api<VerificationStatus[]>(path + '/verification-jobs');
    if (!active.current) return;
    setJobs(values);
    const current = await api<CommercePlan>(path);
    if (active.current) onPlan(current);
  }, [api, path, onPlan]);
  useEffect(() => {
    active.current = true;
    void refresh().catch(e => {if (active.current) setError(e.message);});
    return () => {active.current = false;};
  }, [refresh]);
  const current = jobs[0];
  useEffect(() => {
    if (!current || !['QUEUED', 'RUNNING', 'COLLECTED'].includes(current.state)) return;
    const timer = window.setInterval(() => {void refresh().catch(e => {if (active.current) setError(e.message);});}, 2500);
    return () => window.clearInterval(timer);
  }, [current?.state, refresh]);
  async function run(action: 'start' | 'cancel' | 'reconcile' | 'resume_staging') {
    if (busy) return;
    setBusy(true); setError('');
    try {
      if (action === 'start') {
        if (!plan.revision) throw new Error('计划版本缺失，请刷新团队状态');
        const pending = request.current || {revision: plan.revision, id: crypto.randomUUID()};
        request.current = pending;
        await api<VerificationStatus>(path + '/verification-jobs', {method: 'POST', body: JSON.stringify({
          expected_revision: pending.revision, client_request_id: pending.id})});
        request.current = null;
      } else if (current) {
        await api<VerificationStatus>(path + `/verification-jobs/${current.id}/${action}`, {method: 'POST',
          body: JSON.stringify({expected_revision: current.revision})});
      }
      await refresh();
    } catch (e) {if (active.current) setError(e instanceof Error ? e.message : '验证操作未完成，请刷新核对');}
    finally {if (active.current) setBusy(false);}
  }
  const allowed = plan.state === 'VERIFYING' || (plan.state === 'BLOCKED' && plan.error_code === 'VERIFICATION_UNAVAILABLE');
  return <section className="commerce-import" data-testid="verification-panel"><h3>{ui("店铺验证")}</h3>
    <p>{ui("验证在后台运行。生成报告后进入审查，正式发布仍需单独确认。")}</p>
    {error && <p role="alert" className="error">{uiFeedback(error)}</p>}
    {current ? <><p role="status">{ui(states[current.state])}{current.error_code ? ` · ${current.error_code}` : ''}</p>
      <ol>{phases.map(([id, label]) => <li key={id}>{ui(label)} · {current.completed_phases.includes(id) ? ui("已完成") : current.phase === id ? ui("进行中") : ui("待执行")}</li>)}</ol>
      {current.state === 'NEEDS_RECONCILIATION' && <><button disabled={busy} onClick={() => void run('reconcile')}>{ui("只读核对中断结果")}</button><p>{ui("先核对后台记录。刷新只读取状态，不会重发部署或下单。")}</p></>}
      {current.state === 'NEEDS_RECONCILIATION' && current.phase === 'staging' && <><p>{ui("只读核对成功后，可明确继续未发送的预览步骤。原授权过期或仍有未知操作时会拒绝续跑。")}</p><button disabled={busy} onClick={() => void run('resume_staging')}>{ui("继续尚未发送的预览步骤")}</button></>}
      {!current.cancel_requested && current.state !== 'CANCELLED' && <button disabled={busy} onClick={() => void run('cancel')}>{ui("取消此验证")}</button>}
    </> : <button disabled={busy || !allowed} onClick={() => void run('start')}>{ui("开始后台验证")}</button>}
    {' '}<button disabled={busy} onClick={() => void refresh().catch(e => setError(e.message))}>{ui("刷新验证进度")}</button>
  </section>;
}
