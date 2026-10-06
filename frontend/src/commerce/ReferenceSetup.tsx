import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {ReferenceJob, StoreProject} from '../api.generated';
import type {Api} from './api';

const states: Record<ReferenceJob['state'], string> = {
  RESERVED: '已预留', UNKNOWN: '准备结果未知', READY: '预览站就绪', BLOCKED: '准备受阻',
  CLEANUP_UNKNOWN: '清理结果未知', CLEANED: '已清理',
};

export function ReferenceSetup({api, project, onChanged}: {
  api: Api; project: StoreProject; onChanged: (value: StoreProject) => void;
}) {
  const [jobs, setJobs] = useState<ReferenceJob[]>([]), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [confirmCleanup, setConfirmCleanup] = useState('');
  const live = useRef(true), reservation = useRef<string | null>(null);
  const binding = useRef<{key: string; id: string} | null>(null);
  const path = `/commerce/projects/${project.id}`;
  useEffect(() => {
    let active = true; live.current = true;
    api<ReferenceJob[]>(path + '/reference-jobs').then(value => {if (active) setJobs(value);})
      .catch(e => {if (active) setError(e.message);});
    return () => {active = false; live.current = false;};
  }, [api, path, project.revision]);
  async function run(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {await operation();}
    catch (e) {if (live.current) setError(e instanceof Error ? e.message : '预览站操作未完成，请刷新作业后核对');}
    finally {if (live.current) setBusy(false);}
  }
  async function refresh() {
    const value = await api<ReferenceJob[]>(path + '/reference-jobs');
    if (live.current) setJobs(value);
  }
  function replace(job: ReferenceJob) {
    if (live.current) setJobs(previous => [...previous.filter(value => value.id !== job.id), job]);
  }
  function reserve() {void run(async () => {
    reservation.current ||= crypto.randomUUID();
    const job = await api<ReferenceJob>(path + '/reference-jobs', {method: 'POST', body: JSON.stringify({
      expected_revision: project.revision, client_request_id: reservation.current,
    })});
    replace(job); reservation.current = null;
  });}
  function command(job: ReferenceJob, action: 'provision' | 'verify' | 'recover' | 'cleanup') {void run(async () => {
    const value = await api<ReferenceJob | {site_ready: false}>(path + `/reference-jobs/${job.id}`, {
      method: 'POST', body: JSON.stringify({expected_revision: job.revision, action}),
    });
    if (!live.current) return;
    if ('state' in value) replace(value);
    else {setNotice('已完成只读资源查询；资源存在不代表预览站就绪。'); await refresh();}
    if (action === 'cleanup') {
      setConfirmCleanup('');
      const current = await api<StoreProject>(path);
      if (live.current) onChanged(current);
    }
  });}
  function bind(job: ReferenceJob) {void run(async () => {
    const payload = {connection_id: 'ref-' + job.id, expected_revision: project.revision}, key = JSON.stringify(payload);
    if (binding.current?.key !== key) binding.current = {key, id: crypto.randomUUID()};
    const current = await api<StoreProject>(path + '/connections', {method: 'POST',
      body: JSON.stringify({...payload, client_request_id: binding.current.id})});
    binding.current = null;
    if (live.current) {onChanged(current); setNotice('已绑定预览站。请在团队面板读取店铺上下文后启动流程。');}
  });}
  return <section className="commerce-card" data-testid="reference-setup"><h2>{ui("隔离预览站")}</h2>
    <p>{ui("为这个项目准备独立的 WordPress + WooCommerce 测试站。预览站关闭邮件、外部服务和真实支付；不会复制客户或订单。")}</p>
    <p className="commerce-notice">{ui("需要服务端配置已验证的 Linux/Docker 和离线资源。准备期间保持页面打开；失败后先刷新作业，不自动重新安装。")}</p>
    {error && <p role="alert" className="error">{uiFeedback(error)}</p>}{notice && <p role="status">{uiFeedback(notice)}</p>}
    <button disabled={busy} onClick={reserve}>{ui("预留新的预览站")}</button>{' '}
    <button disabled={busy} onClick={() => void run(refresh)}>{ui("刷新预览作业")}</button>
    {jobs.map(job => {
      const bound = (project.environment_refs || []).some(ref => ref.connector_ref === 'ref-' + job.id);
      return <div key={job.id}><h3>{ui("预览作业 ·")}{ui(states[job.state])}</h3><p>{ui("作业")}{job.id.slice(0, 8)}{ui(" · 版本 ")}{job.revision}</p>
        {job.state === 'RESERVED' && <button disabled={busy || job.project_revision !== project.revision} onClick={() => command(job, 'provision')}>{ui("开始准备预览站")}</button>}
        {job.state === 'UNKNOWN' && <button disabled={busy || job.project_revision !== project.revision} onClick={() => command(job, 'verify')}>{ui("只读核验安装结果")}</button>}
        {['UNKNOWN', 'BLOCKED', 'CLEANUP_UNKNOWN', 'READY'].includes(job.state) && <button disabled={busy} onClick={() => command(job, 'recover')}>{ui("只读查询资源")}</button>}
        {job.state === 'READY' && <button disabled={busy || bound} onClick={() => bind(job)}>{bound ? ui("已绑定此预览站") : ui("绑定就绪的预览站")}</button>}
        {job.state !== 'CLEANED' && <><p>{ui("清理会删除此作业的测试容器和数据。已绑定的连接将解除，原计划失效。")}</p>
          <label><input type="checkbox" checked={confirmCleanup === job.id} disabled={busy}
            onChange={event => setConfirmCleanup(event.target.checked ? job.id : '')}/>{ui("确认删除这份预览测试数据")}</label>{' '}
          <button disabled={busy || confirmCleanup !== job.id} onClick={() => command(job, 'cleanup')}>{job.state === 'CLEANUP_UNKNOWN' ? ui("继续核对并清理") : ui("清理此预览站")}</button></>}
      </div>;
    })}
  </section>;
}
