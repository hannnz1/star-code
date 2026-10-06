import {ui, uiFeedback} from '../i18n';
import {useRef, useState} from 'react';
import type {ImportedProducts, StoreProject} from '../api.generated';
import type {Api} from './api';
import {ProductImages} from './ProductImages';
import {useSessionDraft} from './useSessionDraft';

export function ProductImport({project, imports, api, onSaved}: {
  project: StoreProject; imports: ImportedProducts[]; api: Api; onSaved: (record: ImportedProducts) => void;
}) {
  const [csv, setCsv] = useSessionDraft(`products:${project.id}:${project.revision}`, ''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const pending = useRef<{payload: string; id: string} | null>(null);
  const [mediaIds, setMediaIds] = useState<string[]>([]);
  const [mediaBusy, setMediaBusy] = useState(true);
  async function save() {
    if (busy || mediaBusy) return;
    setBusy(true); setError('');
    const payload = {csv_text: csv, media_ids: mediaIds, expected_revision: project.revision || 1};
    const key = JSON.stringify(payload);
    if (pending.current?.payload !== key) pending.current = {payload: key, id: crypto.randomUUID()};
    try {
      const record = await api<ImportedProducts>(`/commerce/projects/${project.id}/product-imports`,
        {method: 'POST', body: JSON.stringify({...payload, client_request_id: pending.current.id})});
      onSaved(record); pending.current = null;
    } catch (e) {setError(e instanceof Error ? e.message : '商品校验未完成');}
    finally {setBusy(false);}
  }
  return <section className="commerce-card"><h2>{ui("新品准备")}</h2>
    <p>{ui("每批最多 20 件简单实体商品，币种须为")}{project.brief.currency}{ui("。草稿会引用已验证图片；本步骤只保存资料，店铺 SKU 与发布结果在后续验证和审查中核对。")}</p>
    <ProductImages project={project} api={api} onSelected={setMediaIds} onBusyChange={setMediaBusy}/>
    <details><summary>{ui("CSV 格式")}</summary><code>sku,name,price,currency,stock,category,description,image_names</code><p>{ui("第一行为以上列名；image_names 填写已勾选图片的文件名，或留空。价格用十进制，库存用非负整数。")}</p></details>
    <label>{ui("读取 CSV 文件")}<input type="file" accept=".csv,text/csv" onChange={async e => {
      const file = e.target.files?.[0]; if (!file) return;
      if (file.size > 1024 * 1024) {setError('CSV 文件不能超过 1 MiB'); return;}
      setCsv(await file.text()); setError('');
    }}/></label>
    <label htmlFor="merchant-products-csv">{ui("商品 CSV")}</label><textarea id="merchant-products-csv" className="commerce-csv" value={csv} onChange={e => setCsv(e.target.value)} maxLength={1024 * 1024}/>
    <button className="primary" disabled={busy || mediaBusy || !csv.trim()} onClick={() => void save()}>{busy ? ui("正在校验…") : ui("校验并保存草稿")}</button>
    {error && <p className="error commerce-error" role="alert">{uiFeedback(error)}</p>}
    {imports.map(record => <article key={record.id} className="commerce-import">
      <h3>{ui("文件校验通过：")}{record.result.drafts?.length || 0}{' '}{ui("件商品；尚未发布")}</h3>
      {record.project_revision !== (project.revision || 1) && <p className="error">{ui("项目资料已更新，该批草稿需要按当前资料重新校验。")}</p>}
      <div className="commerce-table"><table><thead><tr><th>SKU</th><th>{ui("名称")}</th><th>{ui("价格")}</th><th>{ui("库存")}</th></tr></thead>
        <tbody>{record.result.drafts?.map(product => <tr key={product.sku}><td>{product.sku}</td><td>{product.title}</td><td>{product.currency} {product.price}</td><td>{product.stock}</td></tr>)}</tbody></table></div>
    </article>)}
  </section>;
}
