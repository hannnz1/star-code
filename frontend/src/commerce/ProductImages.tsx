import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {ProjectMedia, StoreProject} from '../api.generated';
import type {Api} from './api';

export function ProductImages({project, api, onSelected, onBusyChange}: {
  project: StoreProject; api: Api; onSelected: (ids: string[]) => void; onBusyChange: (busy: boolean) => void;
}) {
  const [images, setImages] = useState<ProjectMedia[]>([]), [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const live = useRef(true);
  useEffect(() => {
    let cancelled = false; live.current = true;
    api<ProjectMedia[]>(`/commerce/projects/${project.id}/media`).then(records => {
      if (!cancelled) {setImages(records); setSelected(records.map(record => record.id));}
    }).catch(e => {if (!cancelled) setError(e instanceof Error ? e.message : '图片读取未完成');})
      .finally(() => {if (!cancelled) setLoading(false);});
    return () => {cancelled = true; live.current = false;};
  }, [api, project.id]);
  useEffect(() => {onSelected(selected);}, [onSelected, selected]);
  useEffect(() => {onBusyChange(loading || busy);}, [onBusyChange, loading, busy]);
  async function upload(files: File[]) {
    if (busy || loading) return;
    setBusy(true); setError('');
    try {
      for (const file of files) {
        if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || !file.size || file.size > 10 * 1024 * 1024) {
          throw new Error('请选择不超过 10 MiB 的 PNG、JPEG 或 WebP 图片');
        }
        const query = new URLSearchParams({name: file.name, expected_revision: String(project.revision || 1), client_request_id: crypto.randomUUID()});
        const record = await api<ProjectMedia>(`/commerce/projects/${project.id}/media?${query}`,
          {method: 'POST', body: file, headers: {'Content-Type': file.type}});
        if (!live.current) return;
        setImages(previous => [...previous.filter(item => item.id !== record.id), record]);
        setSelected(previous => [...previous.filter(id => id !== record.id), record.id]);
        window.dispatchEvent(new CustomEvent('crew-media-updated',{detail:project.id}));
      }
    } catch (e) {if (live.current) setError(e instanceof Error ? e.message : '图片上传未完成');}
    finally {if (live.current) setBusy(false);}
  }
  return <div className="commerce-images">
    <h3>{ui("商品图片")}</h3><p>{ui("上传后可在 CSV 的 image_names 列填写文件名，多张图片用 | 分隔。每件最多 5 张；项目最多 100 张、共 100 MiB。图片会移除附带元数据。")}</p>
    <label>{ui("商品图片")}<input type="file" multiple accept="image/png,image/jpeg,image/webp" disabled={loading || busy}
      onChange={e => {const files = Array.from(e.target.files || []); e.target.value = ''; void upload(files);}}/></label>
    {(loading || busy) && <p role="status">{loading ? ui("正在读取图片…") : ui("正在验证并保存图片…")}</p>}
    {error && <p className="error commerce-error" role="alert">{uiFeedback(error)}</p>}
    <ul>{images.map(record => <li key={record.id}><label>
      <input type="checkbox" aria-label={ui("使用图片 ") + record.image.name} checked={selected.includes(record.id)}
        onChange={e => setSelected(previous => e.target.checked ? [...previous, record.id] : previous.filter(id => id !== record.id))}/>
      <span>{record.image.name} · {record.width} × {record.height}</span>
    </label></li>)}</ul>
  </div>;
}
