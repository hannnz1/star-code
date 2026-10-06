import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, StoreProject, SiteBlueprint as Blueprint} from '../api.generated';
import type {Api} from './api';
import {ShippingRulesEditor} from './ShippingRulesEditor';
import {CategoryNavigationEditor} from './CategoryNavigationEditor';

const missingNames: Record<string, string> = {'merchant_supplied_policies.shipping': '运输政策',
  'merchant_supplied_policies.returns': '退货政策', 'merchant_supplied_policies.privacy': '隐私政策',
  shipping_confirmed: '运输设置确认', payment_confirmed: '付款设置确认', store_currency: '店铺币种确认',
  owned_block_theme: '受支持的店铺主题'};

export function SiteBlueprint({api, project, onPrepared}: {api: Api; project: StoreProject; onPrepared?:(plan:CommercePlan)=>void}) {
  const [plans, setPlans] = useState<CommercePlan[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const requestId = useRef<string | null>(null);
  const [editing, setEditing] = useState<Blueprint | null>(null), [notice, setNotice] = useState('');
  const [sourceBusy, setSourceBusy] = useState(false);
  const scope = `${project.id}:${project.revision}`;
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const loading = loadedScope !== scope;
  const activeScope = useRef(scope); activeScope.current = scope;
  const generation = useRef(0);
  const drafts = plans.filter(p => p.kind === 'build_site' && p.blueprint && !p.steps?.length);
  const current = [...drafts].reverse().find(p => p.state === 'NEEDS_INPUT');
  const history = drafts.filter(p => p.id !== current?.id);
  useEffect(() => {
    let active = true;
    generation.current++;
    setLoadedScope(null); setPlans([]); setEditing(null); setError(''); setNotice(''); setSourceBusy(false); setBusy(false); requestId.current = null;
    api<CommercePlan[]>(`/commerce/projects/${project.id}/plans`).then(value => {if (active) setPlans(value);})
      .catch(e => {if (active) setError(e.message);})
      .finally(() => {if (active) setLoadedScope(scope);});
    return () => {active = false; generation.current++;};
  }, [api, project.id, project.revision]);
  async function save() {
    if (!current || !editing || busy || loading || sourceBusy) return;
    setBusy(true); setError(''); setNotice('');
    const startedScope = scope;
    const startedGeneration = generation.current;
    try {
      const plan = await api<CommercePlan>(`/commerce/projects/${project.id}/site-blueprint/${current.id}`, {method: 'PATCH',
        body: JSON.stringify({expected_revision: project.revision, expected_plan_revision: current.revision,
          pages: editing.pages, navigation: editing.navigation})});
      if (activeScope.current !== startedScope || generation.current !== startedGeneration) return;
      setPlans(old => old.map(p => p.id === plan.id ? plan : p)); setEditing(null);
      setNotice('结构草稿已保存，后续建站将使用此方案。'); onPrepared?.(plan);
    } catch (e) {if (activeScope.current === startedScope && generation.current === startedGeneration) setError(e instanceof Error ? e.message : '结构草稿未完成');}
    finally {if (activeScope.current === startedScope && generation.current === startedGeneration) setBusy(false);}
  }
  async function prepare() {
    if (busy || loading) return;
    const startedScope = scope;
    const startedGeneration = generation.current;
    setBusy(true); setError(''); setNotice('');
    requestId.current ||= crypto.randomUUID();
    try {
      const plan = await api<CommercePlan>(`/commerce/projects/${project.id}/site-blueprint`, {method: 'POST',
        body: JSON.stringify({expected_revision: project.revision || 1, client_request_id: requestId.current})});
      if (activeScope.current !== startedScope || generation.current !== startedGeneration) return;
      setPlans(old => [...old.filter(p => p.id !== plan.id), plan]); requestId.current = null; onPrepared?.(plan);
    } catch (e) {if (activeScope.current === startedScope && generation.current === startedGeneration) setError(e instanceof Error ? e.message : '结构草稿未完成');}
    finally {if (activeScope.current === startedScope && generation.current === startedGeneration) setBusy(false);}
  }
  function summary(plan: CommercePlan) {
    const fields = plan.blueprint!.required_settings?.missing_fields;
    const missing = Array.isArray(fields) ? fields.filter((f): f is string => typeof f === 'string') : [];
    return <><ol className="commerce-blueprint">{plan.blueprint!.pages.map(page => <li key={page.kind}>{page.title}</li>)}</ol>
      <p>{ui("导航：")}{(plan.blueprint!.navigation || []).map(item => item.label).join(' · ')}</p>
      {!!missing.length && <p>{ui("待确认：")}{missing.map(field => missingNames[field] ? ui(missingNames[field]) : field).join('、')}</p>}</>;
  }
  return <section className="commerce-card" data-testid="site-blueprint"><h2>{ui("建站方案")}</h2>
    <p>{ui("先确定七类页面与导航。结构草稿尚未创建站点；店铺、政策、运输和付款配置需要在生成网站前确认。")}</p>
    {!current && <button className="primary" disabled={busy || loading} onClick={() => void prepare()}>{busy ? ui("正在准备…") : ui("生成结构草稿")}</button>}
    {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {notice && <p role="status">{ui(notice)}</p>}
    {current && <article className="commerce-import" data-testid="current-blueprint"><h3>{ui("当前结构草稿")}</h3>
      <p>{ui("7 类页面 · 结构草稿，尚未建站")}</p>
      {!editing ? <>{summary(current)}<button disabled={busy || loading || sourceBusy} onClick={() => {setEditing(structuredClone(current.blueprint!)); setNotice('');}}>{ui("编辑结构草稿")}</button></> :
        <form className="crew-blueprint-editor" onSubmit={e => {e.preventDefault(); void save();}}>
          <p>{ui("修改页面名称、路径和导航。七类必要页面会保留；保存不会立即发布网站。")}</p>
          <fieldset disabled={busy || loading}>
          {editing.pages.map((page, index) => {
            const nav = (editing.navigation || []).find(item => item.slug === page.slug);
            return <div className="crew-blueprint-row" key={page.kind}>
              <label>{ui("页面名称")}<input aria-label={`${ui("页面名称")} ${index + 1}`} required maxLength={160} value={page.title}
                onChange={e => setEditing({...editing, pages: editing.pages.map(p => p.kind === page.kind ? {...p, title: e.target.value} : p)})}/></label>
              <label>{ui("页面路径")}<input aria-label={`${ui("页面路径")} ${index + 1}`} required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={page.slug}
                onChange={e => setEditing({...editing, pages: editing.pages.map(p => p.kind === page.kind ? {...p, slug:e.target.value} : p),
                  navigation: (editing.navigation || []).map(item => item.slug === page.slug ? {...item, slug:e.target.value} : item)})}/></label>
              {page.kind !== 'product' && <label className="crew-blueprint-nav"><input type="checkbox" aria-label={`${ui("显示在导航")} ${index + 1}`} checked={!!nav}
                onChange={e => setEditing({...editing, navigation: e.target.checked ? [...(editing.navigation || []), {slug:page.slug,label:page.title}] : (editing.navigation || []).filter(item => item.slug !== page.slug)})}/>{ui("显示在导航")}</label>}
              {nav && <label>{ui("导航名称")}<input aria-label={`${ui("导航名称")} ${index + 1}`} required maxLength={160} value={nav.label}
                onChange={e => setEditing({...editing, navigation: (editing.navigation || []).map(item => item.slug === page.slug ? {...item,label:e.target.value} : item)})}/></label>}
            </div>;
          })}
          <h4>{ui("导航顺序")}</h4>
          {(editing.navigation || []).map((item,i)=><div key={item.slug}>{item.label} <button type="button" aria-label={`${ui("导航上移")} ${i+1}`} disabled={i===0} onClick={()=>{const navigation=[...(editing.navigation||[])];[navigation[i-1],navigation[i]]=[navigation[i],navigation[i-1]];setEditing({...editing,navigation});}}>↑</button><button type="button" aria-label={`${ui("导航下移")} ${i+1}`} disabled={i===(editing.navigation||[]).length-1} onClick={()=>{const navigation=[...(editing.navigation||[])];[navigation[i+1],navigation[i]]=[navigation[i],navigation[i+1]];setEditing({...editing,navigation});}}>↓</button></div>)}
          <div className="commerce-actions"><button type="submit" className="primary" disabled={!editing.navigation?.length}>{busy ? ui("正在保存…") : ui("保存结构草稿")}</button>
            <button type="button" onClick={() => setEditing(null)}>{ui("取消")}</button></div>
          </fieldset>
        </form>}
      <ShippingRulesEditor key={`${scope}:${current.id}:${current.revision}`} api={api} project={project} plan={current} disabled={busy || loading || !!editing || sourceBusy} onBusy={setSourceBusy} onSaved={plan=>{setPlans(old=>old.map(value=>value.id===plan.id?plan:value));setNotice('配送草稿已保存，尚未在店铺生效。');onPrepared?.(plan);}}/>
      <CategoryNavigationEditor key={`category:${scope}:${current.id}:${current.revision}`} api={api} project={project} plan={current} disabled={busy || loading || !!editing || sourceBusy} onBusy={setSourceBusy} onSaved={plan=>{setPlans(old=>old.map(value=>value.id===plan.id?plan:value));setNotice('分类导航草稿已保存，尚未在店铺生效。');onPrepared?.(plan);}}/>
    </article>}
    {!!history.length && <details className="commerce-import" data-testid="blueprint-history"><summary>{ui("历史结构草稿")} ({history.length})</summary>
      <p>{ui("历史草稿仅供查看，后续建站使用当前方案。")}</p>
      {[...history].reverse().map(plan => <article key={plan.id}><h4>{ui("结构草稿")} · {plan.id.slice(0, 8)}</h4>
        {plan.state === 'STALE' && <p>{ui("项目资料已更新，请重新生成结构草稿。")}</p>}{summary(plan)}</article>)}
    </details>}
  </section>;
}
