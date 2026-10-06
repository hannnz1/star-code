import {ui, uiFeedback} from '../i18n';
import {useRef, useState} from 'react';
import type {ProjectExport as ExportBundle, StoreProject} from '../api.generated';
import type {Api} from './api';

export function ProjectExport({api, project}: {api: Api; project: StoreProject}) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const pending = useRef(false);
  async function download() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setMessage(''); setError('');
    try {
      const bundle = await api<ExportBundle>(`/commerce/projects/${project.id}/export?revision=${project.revision}`);
      const bytes = Uint8Array.from(atob(bundle.archive_base64), value => value.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], {type: 'application/zip'}));
      const link = document.createElement('a');
      link.href = url; link.download = `muse-project-${project.id}-r${project.revision}.zip`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('项目资料已导出');
    } catch (value) {setError(value instanceof Error ? value.message : '导出未完成，请重试');}
    finally {pending.current = false; setBusy(false);}
  }
  return <section className="commerce-card"><h2>{ui("保存项目资料")}</h2>
    <p>{ui("下载品牌需求、建站方案和当前商品草稿。可生成的主题包也会一并保存。")}</p>
    <p>{ui("不包含店铺凭据、客户或订单；导出不会部署网站，恢复到另一店铺仍需重新配置和验证。")}</p>
    <button disabled={busy} onClick={download}>{busy ? ui("正在准备资料…") : ui("下载项目资料")}</button>
    {message && <p role="status">{uiFeedback(message)}</p>}{error && <p role="alert" className="error">{uiFeedback(error)}</p>}
  </section>;
}
