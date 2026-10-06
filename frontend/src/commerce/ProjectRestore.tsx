import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {RestoredProject, StoreProject, WorkspaceView} from '../api.generated';
import type {Api} from './api';

export function ProjectRestore({api, workspaces, workspace, onRestored}: {
  api: Api; workspaces: WorkspaceView[]; workspace: string; onRestored: (project: StoreProject) => void;
}) {
  const [target, setTarget] = useState(workspace), [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const live = useRef(true), sending = useRef(false);
  const pending = useRef<{key: string; id: string} | null>(null);
  useEffect(() => {live.current = true; return () => {live.current = false;};}, []);
  async function restore() {
    if (sending.current || !file || !target) return;
    sending.current = true; setBusy(true); setError('');
    try {
      if (!file.size || file.size > 16 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.zip')) {
        throw new Error('请选择不超过 16 MiB 的 Crew 项目 ZIP 文件');
      }
      const bytes = await file.arrayBuffer();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
      const key = target + ':' + hash;
      if (pending.current?.key !== key) pending.current = {key, id: crypto.randomUUID()};
      const query = new URLSearchParams({workspace_id: target, client_request_id: pending.current.id});
      const result = await api<RestoredProject>(`/commerce/projects/restore?${query}`,
        {method: 'POST', body: new Blob([bytes]), headers: {'Content-Type': 'application/zip'}});
      if (!live.current) return;
      pending.current = null; onRestored(result.project);
    } catch (value) {if (live.current) setError(value instanceof Error ? value.message : '恢复未完成，请检查项目资料');}
    finally {sending.current = false; if (live.current) setBusy(false);}
  }
  return <section className="commerce-card"><h2>{ui("恢复项目资料")}</h2>
    <p>{ui("将 Crew 导出的品牌需求、商品、图片和主题代码恢复为新项目。新店铺需要重新连接、验证和批准。")}</p>
    <label>{ui("恢复到工作区")}<select value={target} disabled={busy} onChange={e => setTarget(e.target.value)}>
      {workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>
    <label>{ui("项目资料 ZIP")}<input type="file" accept=".zip,application/zip" disabled={busy}
      onChange={e => {setFile(e.target.files?.[0] || null); setError('');}}/></label>
    <button disabled={busy || !file || !target} onClick={() => void restore()}>{busy ? ui("正在校验并恢复…") : ui("恢复为新商家项目")}</button>
    {error && <p className="error commerce-error" role="alert">{uiFeedback(error)}</p>}
  </section>;
}
