import {StoreReadiness} from './StoreReadiness';
import {ProductEditor} from './ProductEditor';
import {StoreEditor} from './editor/StoreEditor';
import {ui, uiFeedback} from '../i18n';
import {useCallback, useEffect, useRef, useState} from 'react';
import {ArrowUpRight, LayoutTemplate, Package, Plus, Settings2} from 'lucide-react';
import type {CommercePlan, ImportedProducts, SiteBrief, StoreProject, WorkspaceView} from '../api.generated';
import type {Api} from './api';
import {readCrewRoute,type CommerceSection} from './navigation';
import {SiteWizard} from './SiteWizard';
import {ProductImport} from './ProductImport';
import {SiteBlueprint} from './SiteBlueprint';
import {StoreTeam, type TeamOpenRequest} from './StoreTeam';
import {planLane, planNeedsAttention, planNextAction} from './TaskBoard';
import {ProjectExport} from './ProjectExport';
import {ProjectRestore} from './ProjectRestore';
import {ReferenceSetup} from './ReferenceSetup';
import {StorePreviewPanel} from './StorePreview';
import {ManagerPanel} from './ManagerPanel';
import {FlowJourney} from './FlowJourney';
import {BrandSettings} from './BrandSettings';
import {ProjectManagement} from './ProjectManagement';
import './studio.css';

export function CommerceHome({api, workspaces, workspace, onOpenTask, active=true, section='overview', selectedProjectId='', onSection, onContext, onProject, onMemory, onWorkspace, model}: {
  api:Api; workspaces:WorkspaceView[]; workspace:string; onOpenTask?:(id:string)=>void; active?:boolean;
  section?:CommerceSection; selectedProjectId?:string; onSection?:(section:CommerceSection)=>void;
  onContext?:(projects:StoreProject[],id:string)=>void; onProject?:(id:string,section?:CommerceSection)=>void;
  onMemory?:()=>void; onWorkspace?:()=>void; model?:string;
}) {
  const [projects,setProjects]=useState<StoreProject[]>([]), [loaded,setLoaded]=useState(false);
  const [imports,setImports]=useState<ImportedProducts[]>([]), [plans,setPlans]=useState<CommercePlan[]>([]);
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [manager,setManager]=useState(false);
  const [openRequest,setOpenRequest]=useState<TeamOpenRequest|null>(null);
  const pending=useRef<{payload:string;id:string}|null>(null);
  const selected=projects.find(p=>p.id===selectedProjectId)||null;
  const current=useRef(selected); current.current=selected;
  const go=(value:CommerceSection)=>onSection?.(value);
  useEffect(()=>{
    let live=true;
    api<StoreProject[]>('/commerce/projects').then(value=>{
      if(!live)return;setProjects(value);setLoaded(true);
      const id=selectedProjectId||(!readCrewRoute().creating?value[0]?.id||'':'');
      onContext?.(value,id);
    }).catch(e=>{if(live){setLoaded(true);setError(e.message);}});
    return()=>{live=false;};
  },[api]);
  useEffect(()=>{const id=selectedProjectId||(loaded&&!readCrewRoute().creating?projects[0]?.id||'':'');onContext?.(projects,id);},[projects,selectedProjectId,onContext,loaded]);
  useEffect(()=>{
    let live=true;setImports([]);setPlans([]);setOpenRequest(null);setManager(false);
    if(selected) {
      api<ImportedProducts[]>(`/commerce/projects/${selected.id}/product-imports`).then(value=>{if(live)setImports(value);}).catch(e=>{if(live)setError(e.message);});
      api<CommercePlan[]>(`/commerce/projects/${selected.id}/plans`).then(value=>{if(live)setPlans(value);}).catch(e=>{if(live)setError(e.message);});
    }
    return()=>{live=false;};
  },[api,selected?.id,selected?.revision]);
  const updatePlans=useCallback((value:CommercePlan[])=>{
    if(value.every(p=>p.project_id===current.current?.id))setPlans(old=>[...old.filter(p=>!p.steps?.length),...value]);
  },[]);
  async function create(workspaceId:string,brief:SiteBrief) {
    if(busy)return;setBusy(true);setError('');const payload={workspace_id:workspaceId,brief},key=JSON.stringify(payload);
    if(pending.current?.payload!==key)pending.current={payload:key,id:crypto.randomUUID()};
    try {const value=await api<StoreProject>('/commerce/projects',{method:'POST',body:JSON.stringify({...payload,client_request_id:pending.current.id})});
      setProjects(old=>[...old.filter(p=>p.id!==value.id),value]);onProject?.(value.id);pending.current=null;
    }catch(e){setError(e instanceof Error?e.message:'保存未完成');}finally{setBusy(false);}
  }
  function changed(project:StoreProject) {if(project.id===current.current?.id)setProjects(old=>old.map(p=>p.id===project.id?project:p));}
  async function refreshProjects(preferred?:string) {
    const value=await api<StoreProject[]>('/commerce/projects');
    setProjects(value);onProject?.(preferred||value.find(p=>p.id===selectedProjectId)?.id||value[0]?.id||'','settings');
  }
  function prepare(kind:'build_site'|'launch_products') {
    setOpenRequest({id:crypto.randomUUID(),kind});go('team');
  }
  const validImports=imports.filter(i=>i.project_id===selected?.id&&i.project_revision===selected?.revision);
  const teamPlans=plans.filter(p=>p.project_id===selected?.id&&!!p.steps?.length);
  const attention=teamPlans.filter(p=>planNeedsAttention(p)||planLane(p)==='ready');
  const preview=teamPlans.filter(p=>p.code_revision&&!['STALE','CANCELLED'].includes(p.state||'')).at(-1);
  if(!loaded)return <p className="crew-loading" role="status">{ui('正在加载商家工作台…')}</p>;
  return <div className="commerce-home commerce-studio crew-workspace">
    <header className="studio-header"><div><span className="studio-kicker">Crew / WordPress + WooCommerce</span>
      <h1>{selected?selected.brief.brand_name:ui('创建你的第一间店铺')}</h1>
      <p>{selected?ui('建站、上新和团队任务，都有清晰的下一步。'):ui('准备品牌资料，或先进入开发空间完成编程任务。')}</p></div>
      <div className="crew-header-actions">{selected&&<button onClick={()=>setManager(true)}>{ui('店长助手')}</button>}
        <button className="studio-new-project" onClick={()=>{onProject?.('');setError('');}}><Plus size={16}/>{ui('新建商家项目')}</button></div></header>
    {error&&<p className="error commerce-error" role="alert">{uiFeedback(error)}</p>}
    {selectedProjectId&&!selected&&<p role="alert">{ui('所选店铺不存在或无权访问，请重新选择。')}</p>}
    {!selected?section==='settings'?<section className="crew-settings"><h2>{ui('设置')}</h2><div className="crew-settings-shortcuts"><button onClick={onMemory}>{ui('偏好与记忆')}</button><button onClick={onWorkspace}>{ui('工作区管理')}</button></div><section className="commerce-card"><h3>{ui('模型与用量')}</h3><p>{model||ui('未配置')}</p><p>{ui('用量可在各任务详情查看；汇总费用暂不可用。')}</p></section><ProjectManagement api={api} project={null} active={active&&section==='settings'} onRefresh={refreshProjects}/></section>:<div className="crew-onboarding"><SiteWizard workspaces={workspaces} workspace={workspace} busy={busy} onSave={create}/>
      <ProjectRestore api={api} workspaces={workspaces} workspace={workspace} onRestored={project=>{setProjects(old=>[...old.filter(p=>p.id!==project.id),project]);onProject?.(project.id);}}/></div>:<div className="crew-sections">
      <section hidden={section!=='overview'} data-testid="merchant-overview" className="studio-overview">
        <p className="crew-store-status">{ui('已登记 {0} 个连接；连接状态以当前版本上下文和验证结果为准。',[selected.environment_refs?.length||0])}</p>
        <div className="crew-overview-heading"><h2>{ui('今天需要你处理什么？')}</h2><span>{selected.brief.language} · {selected.brief.currency}</span></div>
        <section className="crew-attention"><h3>{ui('待处理事项')} <span>{attention.length}</span></h3>
          {!attention.length?<p>{ui('当前没有待处理的团队任务。可以开始建站或准备新品。')}</p>:attention.map(plan=><button key={plan.id} onClick={()=>{setOpenRequest({id:crypto.randomUUID(),planId:plan.id});go('team');}}>
            <span>{plan.kind==='build_site'?ui('建站'):ui('新品上线')}<small>{planNextAction(plan)}</small></span><ArrowUpRight size={17}/></button>)}</section>
        <div className="studio-flow-cards"><button onClick={()=>go('website')}><LayoutTemplate size={22}/><span><b>{ui('搭建你的独立站')}</b><small>{ui('品牌、结构、团队执行、预览与发布。')}</small></span><ArrowUpRight size={18}/></button>
          <button onClick={()=>go('products')}><Package size={22}/><span><b>{ui('准备下一件新品')}</b><small>{ui('商品资料、内容确认、审查与上线。')}</small></span><ArrowUpRight size={18}/></button></div>
        <section className="studio-canvas"><div className="studio-canvas-toolbar">{ui('网站预览')}<span>{ui('对应任务与封存版本')}</span></div>
          {preview?<StorePreviewPanel key={`${selected.id}:${selected.revision}:${preview.id}:${preview.revision}`} api={api} projectId={selected.id} plan={preview}/>:<div className="crew-preview-empty"><LayoutTemplate size={32}/><h3>{ui('你的店铺预览会出现在这里')}</h3><p>{ui('完成网站代码后，读取真实截图并检查对应版本。')}</p><button onClick={()=>go('website')}>{ui('先准备建站方案')}</button></div>}</section>
        <h3>{ui('最近团队任务')}</h3><div className="crew-recent-tasks">{teamPlans.slice(-4).reverse().map(plan=><button key={plan.id} onClick={()=>{setOpenRequest({id:crypto.randomUUID(),planId:plan.id});go('team');}}><b>{plan.kind==='build_site'?ui('建站'):ui('新品上线')}</b><span>{planNextAction(plan)}</span></button>)}{!teamPlans.length&&<p>{ui('保存第一份计划草稿，开始团队协作。')}</p>}</div>
      </section>
      <section hidden={section!=='website'} data-testid="build-site-flow"><FlowJourney kind="build_site" project={selected} plans={plans.filter(p=>p.project_id===selected.id)} imports={validImports} onTeam={()=>prepare('build_site')} onSettings={()=>go('settings')} onReview={plan=>{setOpenRequest({id:crypto.randomUUID(),planId:plan.id,tab:'review'});go('team');}}/>
        <StoreEditor key={'editor-'+selected.id} api={api} project={selected}/><StoreReadiness api={api} project={selected} onAction={value=>{if(value==='connection'){setOpenRequest({id:crypto.randomUUID(),connection:true});go('team');}else go(value as CommerceSection);}}/><SiteBlueprint key={'blueprint-'+selected.id} api={api} project={selected} onPrepared={plan=>{if(current.current?.id===plan.project_id && current.current.revision===selected.revision)setPlans(old=>[...old.filter(p=>p.id!==plan.id),plan]);}}/></section>
      <section hidden={section!=='products'} data-testid="launch-products-flow"><FlowJourney kind="launch_products" project={selected} plans={plans.filter(p=>p.project_id===selected.id)} imports={validImports} onTeam={()=>prepare('launch_products')} onSettings={()=>go('settings')} onReview={plan=>{setOpenRequest({id:crypto.randomUUID(),planId:plan.id,tab:'review'});go('team');}}/>
        <ProductEditor api={api} project={selected} imports={imports} onSaved={record=>setImports(old=>[...old.filter(r=>r.id!==record.id),record])}/><ProductImport key={selected.id} project={selected} imports={imports} api={api} onSaved={record=>{if(current.current?.id===record.project_id)setImports(old=>[...old.filter(r=>r.id!==record.id),record]);}}/></section>
      <section hidden={section!=='team'}><StoreTeam key={'team-'+selected.id} api={api} project={selected} imports={imports} active={active&&section==='team'} openRequest={openRequest} onChanged={changed} onPlansChanged={updatePlans} onOpenTask={onOpenTask}/></section>
      <section hidden={section!=='settings'} className="crew-settings"><h2>{ui('设置')}</h2><div className="crew-settings-shortcuts"><button onClick={onMemory}>{ui('偏好与记忆')}</button><button onClick={onWorkspace}>{ui('工作区管理')}</button><button onClick={()=>{setOpenRequest({id:crypto.randomUUID(),connection:true});go('team');}}>{ui('店铺连接')}</button></div>
        <section className="commerce-card"><h3>{ui('模型与用量')}</h3><p>{model||ui('未配置')}</p><p>{ui('用量可在各任务详情查看；汇总费用暂不可用。')}</p></section>
        <BrandSettings key={`${selected.id}:${selected.revision}`} api={api} project={selected} onChanged={changed}/>
        <ReferenceSetup key={'reference-'+selected.id} api={api} project={selected} onChanged={changed}/>
        <ProjectExport key={'export-'+selected.id+'-'+selected.revision} api={api} project={selected}/>
        <ProjectManagement key={'management-'+selected.id} api={api} project={selected} active={active&&section==='settings'} onRefresh={refreshProjects}/></section>
      <ManagerPanel key={selected.id} api={api} project={selected} section={section} imports={validImports} open={manager&&active} onClose={()=>setManager(false)} onDraft={draft=>{setManager(false);setOpenRequest({id:crypto.randomUUID(),draft});go('team');}}/>
    </div>}
  </div>;
}
