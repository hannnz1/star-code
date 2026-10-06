import {useEffect, useState} from 'react';
import type {StoreProject} from '../api.generated';
import {ui, uiFeedback} from '../i18n';
import type {Api} from './api';
import {WorkspaceDialog} from './WorkspaceDialog';

export function ProjectManagement({api, project, active, onRefresh}: {api:Api; project:StoreProject|null; active:boolean; onRefresh:(id?:string)=>Promise<void>}) {
  const [archived,setArchived]=useState<StoreProject[]>([]), [target,setTarget]=useState<StoreProject|null>(null);
  const [name,setName]=useState(''), [busy,setBusy]=useState(false), [error,setError]=useState('');
  useEffect(()=>{if(!active){setTarget(null);return;}let live=true;
    api<StoreProject[]>('/commerce/archived-projects').then(value=>{if(live)setArchived(value);}).catch(e=>{if(live)setError(e.message);});
    return()=>{live=false;};
  },[api,active,project?.id]);
  async function run(action:'archive'|'restore'|'delete', item:StoreProject) {
    if(busy)return;setBusy(true);setError('');
    try {
      await api(`/commerce/projects/${item.id}${action==='delete'?'':'/'+action}`, {method:action==='delete'?'DELETE':'POST',body:JSON.stringify({expected_revision:item.revision,...(action==='delete'?{confirmation_name:name}:{})})});
      if(action==='delete') {
        try {for(const key of Object.keys(sessionStorage)) {
          if(['brand','products','manager-form','team-form'].some(scope=>key.startsWith(`crew-draft:${scope}:${item.id}:`)))sessionStorage.removeItem(key);
        }}catch{/* Disabled storage must not turn successful deletion into a failure. */}
      }
      setTarget(null);setName('');
      setArchived(await api<StoreProject[]>('/commerce/archived-projects'));
      await onRefresh(action==='restore'?item.id:undefined);
    } catch(e){setError(e instanceof Error?e.message:'商家操作未完成');}finally{setBusy(false);}
  }
  function confirm(item:StoreProject){setError('');setName('');setTarget(item);}
  return <section className="commerce-card crew-project-management" data-testid="project-management"><h3>{ui('店铺管理')}</h3>
    <p>{ui('归档可恢复。永久删除仅清理 Crew 本地商家记录；远程网站、工作区文件和开发任务日志保留。')}</p>
    {error&&!target&&<p role="alert" className="error">{uiFeedback(error)}</p>}
    {project&&<div className="crew-project-actions"><button disabled={busy} onClick={()=>run('archive',project)}>{ui('归档店铺')}</button><button className="crew-danger" disabled={busy} onClick={()=>confirm(project)}>{ui('永久删除店铺')}</button></div>}
    <div data-testid="archived-projects"><h4>{ui('已归档店铺')}</h4>{!archived.length?<p>{ui('暂无已归档店铺')}</p>:archived.map(item=><div className="crew-archived-row" key={item.id}><strong>{item.brief.brand_name}</strong><button disabled={busy} onClick={()=>run('restore',item)}>{ui('恢复店铺')}</button><button className="crew-danger" disabled={busy} onClick={()=>confirm(item)}>{ui('永久删除店铺')}</button></div>)}</div>
    <WorkspaceDialog open={!!target&&active} title={ui('永久删除店铺')} subtitle={target?.brief.brand_name} busy={busy} onClose={()=>setTarget(null)} backLabel={ui('返回设置')}>
      <p>{ui('此操作不可撤销。删除前可在设置中导出项目备份。')}</p><p>{ui('有运行中任务、待核对结果或未清理的预览环境时，操作会被阻止。')}</p>
      <label className="crew-delete-confirm">{ui('输入店铺名称确认')}<input value={name} onChange={e=>setName(e.target.value)} disabled={busy}/></label>
      {error&&<p role="alert" className="error">{uiFeedback(error)}</p>}
      <button className="crew-danger" disabled={busy||name!==target?.brief.brand_name} onClick={()=>target&&run('delete',target)}>{ui('确认永久删除')}</button>
    </WorkspaceDialog>
  </section>;
}
