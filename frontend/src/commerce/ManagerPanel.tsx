import {ui,uiFeedback} from '../i18n';
import {useEffect,useRef,useState} from 'react';
import type {CommerceTaskDraft,ImportedProducts,StoreContext,StoreProject} from '../api.generated';
import type {Api} from './api';
import type {CommerceSection} from './navigation';
import {WorkspaceDialog} from './WorkspaceDialog';
import {useSessionDraft} from './useSessionDraft';

export function ManagerPanel({api,project,section,imports,open,onClose,onDraft}: {
  api:Api;project:StoreProject;section:CommerceSection;imports:ImportedProducts[];open:boolean;
  onClose:()=>void;onDraft:(draft:CommerceTaskDraft)=>void;
}) {
  const [inputs,setInputs]=useSessionDraft(`manager-form:${project.id}:${project.revision}`, {goal:'',kind:'build_site' as 'build_site'|'launch_products',importId:'',limit:'10'});
  const {goal,kind,importId,limit}=inputs;
  const setGoal=(goal:string)=>setInputs(old=>({...old,goal}));
  const setKind=(kind:'build_site'|'launch_products')=>setInputs(old=>({...old,kind}));
  const setImportId=(importId:string)=>setInputs(old=>({...old,importId}));
  const setLimit=(limit:string)=>setInputs(old=>({...old,limit}));
  const [busy,setBusy]=useState(false);
  const [context,setContext]=useState<StoreContext|null>(null),[contextError,setContextError]=useState('');
  const [error,setError]=useState(''),[draft,setDraft]=useState<CommerceTaskDraft|null>(null);
  const pending=useRef<{key:string;id:string}|null>(null), generation=useRef(0);
  useEffect(()=>{if(open&&!goal.trim()){setKind(section==='products'?'launch_products':'build_site');setImportId(imports.at(-1)?.id||'');}},[open,section]);
  useEffect(()=>{
    let live=true;generation.current++;setDraft(null);setContext(null);setContextError('');setBusy(false);
    api<StoreContext>(`/commerce/projects/${project.id}/context`).then(value=>{
      if(live&&value.snapshot.project_id===project.id&&value.project_revision===project.revision)setContext(value);
    }).catch(e=>{if(live)setContextError(e.message);});
    return()=>{live=false;generation.current++;};
  },[api,project.id,project.revision]);
  async function prepare() {
    if(busy||!goal.trim())return;
    const epoch=generation.current;setBusy(true);setError('');
    const payload={kind,title:goal.trim().slice(0,160),prompt:goal.trim(),max_requests:Number(limit),import_id:importId||null,
      expected_project_revision:project.revision};
    const key=JSON.stringify(payload);if(pending.current?.key!==key)pending.current={key,id:crypto.randomUUID()};
    try {
      const value=await api<CommerceTaskDraft>(`/commerce/projects/${project.id}/task-drafts`,{method:'POST',body:JSON.stringify({...payload,client_request_id:pending.current.id})});
      if(epoch===generation.current&&value.project_id===project.id&&value.project_revision===project.revision){setDraft(value);pending.current=null;}
    }catch(e){if(epoch===generation.current)setError(e instanceof Error?e.message:'计划草稿保存未完成');}
    finally{if(epoch===generation.current)setBusy(false);}
  }
  const unchanged=draft&&draft.project_revision===project.revision&&draft.prompt===goal.trim()&&draft.kind===kind&&draft.max_requests===Number(limit)&&(draft.import_id||'')===importId;
  return <WorkspaceDialog side open={open} title={ui('店长助手')} subtitle={project.brief.brand_name} backLabel={ui('返回工作台')} onClose={onClose} busy={busy}>
    <section className="commerce-card crew-manager"><div className="crew-manager-context"><b>{project.brief.brand_name}</b><p>{ui('绑定项目版本：{0}',[project.revision])}</p>
      <p>{ui('当前页面：{0}',[ui(({overview:'概览',website:'网站',products:'商品',team:'团队任务',settings:'设置'})[section])])}</p>
      <p>{context?ui('使用该店铺已保存的上下文；执行时重新校验。'):ui('尚无当前版本店铺上下文，可以先保存计划。')}</p>
      {contextError&&<details><summary>{ui('上下文读取详情')}</summary><p>{uiFeedback(contextError)}</p></details>}</div>
      <p>{ui('告诉店长本次目标。先准备计划，再由你确认启动网站开发和商品内容角色。')}</p>
      <label>{ui('交给店长的目标')}<textarea aria-label={ui('交给店长的目标')} value={goal} onChange={e=>setGoal(e.target.value)} maxLength={10000}/></label>
      <label>{ui('工作流')}<select aria-label={ui('工作流')} value={kind} onChange={e=>setKind(e.target.value as typeof kind)}><option value="build_site">{ui('建站准备')}</option><option value="launch_products">{ui('新品上线准备')}</option></select></label>
      <label>{ui('已校验商品批次')}<select value={importId} onChange={e=>setImportId(e.target.value)}><option value="">{ui('稍后选择商品批次')}</option>{imports.map(item=><option key={item.id} value={item.id}>{item.result.drafts?.length||0} · {item.id.slice(0,8)}</option>)}</select></label>
      <label>{ui('共享模型请求上限')}<input type="number" min="1" max="100" value={limit} onChange={e=>setLimit(e.target.value)}/></label>
      <button className="primary" onClick={()=>void prepare()} disabled={busy||!goal.trim()||!Number.isInteger(Number(limit))||Number(limit)<1||Number(limit)>100}>{busy?ui('正在保存…'):ui('准备计划草稿')}</button>
      <p>{ui('保存草稿不会调用模型。启动团队后使用原模型配置和权限规则。')}</p>
      {error&&<p className="error" role="alert">{uiFeedback(error)}</p>}
      {unchanged&&<div className="crew-manager-result" role="status"><h3>{ui('计划草稿已保存')}</h3><ol>{draft.proposed_steps?.map(step=><li key={step}>{ui(step)}</li>)}</ol><button onClick={()=>onDraft(draft)}>{ui('查看计划草稿')}</button></div>}
    </section>
  </WorkspaceDialog>;
}
