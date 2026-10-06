import {useEffect, useRef, useState} from 'react';
import {ui, uiFeedback} from '../i18n';
import type {CategoryNavigation, CategoryNavigationItem, CommercePlan, ImportedProducts, StoreProject} from '../api.generated';
import type {Api} from './api';
import {useSessionDraft} from './useSessionDraft';

export function CategoryNavigationEditor({api, project, plan, disabled, onSaved, onBusy}: {
  api: Api; project: StoreProject; plan: CommercePlan; disabled: boolean; onSaved:(plan:CommercePlan)=>void; onBusy:(value:boolean)=>void;
}) {
  const source = plan.blueprint?.required_settings?.category_navigation as CategoryNavigation | undefined;
  const [batches, setBatches] = useState<ImportedProducts[]>([]), [loading, setLoading] = useState(true);
  const draftKey=`category:${project.id}:${project.revision}:${plan.id}:${JSON.stringify(source || null)}`;
  const [batchId, setBatchId] = useSessionDraft(draftKey+':batch',source?.import_id || '');
  const [items, setItems] = useSessionDraft<CategoryNavigationItem[]>(draftKey+':items',source?.items || []);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true), request = useRef<{body:string;id:string}|null>(null);
  useEffect(() => {
    alive.current = true;
    api<ImportedProducts[]>(`/commerce/projects/${project.id}/product-imports`).then(value => {
      if (!alive.current) return;
      const valid = value.filter(batch => batch.project_revision === project.revision && !(batch.result.errors || []).length);
      setBatches(valid); if (!source && !batchId) setBatchId(valid.at(-1)?.id || '');
    }).catch(e => {if (alive.current) setError(e.message);}).finally(() => {if (alive.current) setLoading(false);});
    return () => {alive.current = false;};
  }, [api, project.id, project.revision]);
  const batch = batches.find(value => value.id === batchId);
  const names = [...new Set((batch?.result.drafts || []).map(product => product.category).filter((name): name is string => !!name))];
  const stale = items.some(item => !names.includes(item.category));
  async function save() {
    if (disabled || busy || loading || !batch || stale) return;
    const body = JSON.stringify({expected_revision:project.revision, expected_plan_revision:plan.revision, plan_id:plan.id,
      navigation:{import_id:batchId,items}});
    if (!request.current || request.current.body !== body) request.current = {body, id:crypto.randomUUID()};
    const frozen = request.current; setBusy(true); onBusy(true); setError('');
    try {
      const result = await api<CommercePlan>(`/commerce/projects/${project.id}/category-navigation`, {method:'PATCH',
        body:JSON.stringify({...JSON.parse(body),client_request_id:frozen.id})});
      if (alive.current) {request.current = null; onSaved(result);}
    } catch (e) {if (alive.current) setError(e instanceof Error ? e.message : 'Error');}
    finally {if (alive.current) {setBusy(false); onBusy(false);}}
  }
  return <section className="crew-category-editor" data-testid="category-navigation-editor"><h3>{ui('分类导航草稿')}</h3>
    <p>{ui('从本次建站的商品批次选择分类，可修改导航名称与顺序。分类链接将在真实分类创建后绑定，不接受任意网址。')}</p>
    {!loading && !batches.length && <p>{ui('请先在商品栏目保存一批商品，并填写商品分类。')}</p>}
    <form onSubmit={e => {e.preventDefault(); void save();}}><fieldset disabled={disabled || busy || loading}>
      <label>{ui('分类商品来源')}<select value={batchId} onChange={e => {setBatchId(e.target.value);setItems([]);setError('');}}><option value="">{ui('选择商品批次')}</option>{batches.map(value => <option key={value.id} value={value.id}>{(value.result.drafts || []).map(product=>product.title).slice(0,3).join(' · ')} ({(value.result.drafts || []).length})</option>)}</select></label>
      {!!batch && !names.length && <p>{ui('此批商品没有分类，请补齐商品分类后重新导入。')}</p>}
      <div className="crew-category-choices">{names.map(name => <label key={name}><input type="checkbox" aria-label={`${ui('分类导航')} ${name}`} checked={items.some(item=>item.category===name)} disabled={!items.some(item=>item.category===name) && items.length>=10} onChange={e=>setItems(old=>e.target.checked?[...old,{category:name,label:name}]:old.filter(item=>item.category!==name))}/>{name}</label>)}</div>
      {items.map((item,i)=><div className="crew-category-row" key={item.category}><span>{item.category}</span><label>{ui('导航名称')}<input aria-label={`${ui('分类导航名称')} ${i+1}`} required maxLength={160} value={item.label} onChange={e=>setItems(old=>old.map((value,index)=>index===i?{...value,label:e.target.value}:value))}/></label><button type="button" aria-label={`${ui('分类导航上移')} ${i+1}`} disabled={i===0} onClick={()=>{const next=[...items];[next[i-1],next[i]]=[next[i],next[i-1]];setItems(next);}}>↑</button><button type="button" aria-label={`${ui('分类导航下移')} ${i+1}`} disabled={i===items.length-1} onClick={()=>{const next=[...items];[next[i+1],next[i]]=[next[i],next[i+1]];setItems(next);}}>↓</button></div>)}
      {stale && <p role="alert">{ui('分类来源已变化，请重新选择商品批次和分类。')}</p>}
      <button className="primary" type="submit" disabled={!batch || stale || JSON.stringify({import_id:batchId,items})===JSON.stringify(source)}>{busy?ui('正在保存…'):ui('保存分类导航')}</button>
    </fieldset></form>{error&&<p role="alert" className="error">{uiFeedback(error)}</p>}
  </section>;
}
