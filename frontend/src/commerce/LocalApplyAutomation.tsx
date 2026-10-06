import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, LocalApplyAutomation as Automation} from '../api.generated';
import type {Api} from './api';

export function LocalApplyAutomation({api, plan}: {api: Api; plan: CommercePlan}) {
  const [value, setValue] = useState<Automation | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0), pending = useRef<{key: string; id: string} | null>(null);
  const path = `/commerce/projects/${plan.project_id}/plans/${plan.id}/local-apply-automation`;
  useEffect(() => {
    const version = ++generation.current;
    setValue(null); setBusy(false); setError(''); pending.current = null;
    const load = () => void api<Automation | null>(path).then(result => {
      if (version === generation.current) setValue(previous => result && (!previous || result.revision >= previous.revision) ? result : previous);
    }).catch(() => {});
    load(); const timer = window.setInterval(load, 5000);
    return () => {generation.current++; window.clearInterval(timer);};
  }, [api, path]);
  async function arm() {
    if (busy || !window.confirm(ui("确认这一次在任务封存代码后自动应用到本地代码基线？将跳过逐次手动应用确认；有效期 24 小时，基线变化或冲突会阻塞。这不会批准店铺发布。"))) return;
    const version = generation.current;
    setBusy(true); setError('');
    try {
      const capacity = await api<{project_revision: number; code_base_revision: number}>(`/commerce/projects/${plan.project_id}/task-capacity`);
      if (version !== generation.current) return;
      const payload = {expected_plan_revision: plan.revision, expected_project_revision: capacity.project_revision,
        expected_head_revision: capacity.code_base_revision};
      const key = JSON.stringify(payload);
      if (pending.current?.key !== key) pending.current = {key, id: crypto.randomUUID()};
      const result = await api<Automation>(path, {method: 'POST', body: JSON.stringify({...payload, client_request_id: pending.current.id})});
      if (version === generation.current) {setValue(result); pending.current = null;}
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '授权未确认，请刷新核对');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function cancel() {
    if (!value || busy) return;
    const version = generation.current;
    setBusy(true); setError('');
    try {
      const result = await api<Automation>(path + '/cancel', {method: 'POST', body: JSON.stringify({expected_revision: value.revision})});
      if (version === generation.current) setValue(result);
    } catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '取消未确认，请刷新核对');}
    finally {if (version === generation.current) setBusy(false);}
  }
  return <section data-testid="local-apply-automation"><h4>{ui("一次性自动应用本地代码")}</h4>
    <p>{ui("仅应用这项任务的静态主题成果。授权 24 小时后过期，项目或代码基线变化、冲突及取消均会阻塞；店铺发布仍需独立审查。")}</p>
    {value && <p role="status">{ui("自动应用状态：")}{value.status}{value.reason ? ` · ${value.reason}` : ''}</p>}
    <button disabled={busy || value?.status === 'ARMED' || value?.status === 'APPLYING' || ['FAILED', 'CANCELLED', 'STALE', 'NEEDS_INPUT'].includes(plan.state || '')}
      onClick={() => void arm()}>{ui("这一次自动应用本地成果")}</button>
    {value?.status === 'ARMED' && <button disabled={busy} onClick={() => void cancel()}>{ui("撤销自动应用授权")}</button>}
    {error && <p role="alert" className="error">{uiFeedback(error)}</p>}
  </section>;
}
