import {ui,uiFeedback} from '../i18n';
import {useState} from 'react';
import type {StoreProject} from '../api.generated';
import type {Api} from './api';
import {useSessionDraft} from './useSessionDraft';
export function BrandSettings({api,project,onChanged}:{api:Api;project:StoreProject;onChanged:(project:StoreProject)=>void}) {
  const [brief,setBrief]=useSessionDraft(`brand:${project.id}:${project.revision}`,project.brief),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function save(){if(busy)return;setBusy(true);setError('');try{
    onChanged(await api<StoreProject>(`/commerce/projects/${project.id}`,{method:'PATCH',body:JSON.stringify({expected_revision:project.revision,brief})}));
  }catch(e){setError(e instanceof Error?e.message:'保存未完成');}finally{setBusy(false);}}
  return <section className="commerce-card"><h2>{ui('品牌资料')}</h2><p>{ui('更新资料会改变项目版本，已有计划与批准需重新核对。')}</p>
    <form onSubmit={e=>{e.preventDefault();void save();}}><div className="commerce-fields">
      <label>{ui('品牌名称')}<input required maxLength={160} value={brief.brand_name} onChange={e=>setBrief({...brief,brand_name:e.target.value})}/></label>
      <label>{ui('网站语言')}<input required maxLength={24} value={brief.language} onChange={e=>setBrief({...brief,language:e.target.value})}/></label>
      <label>{ui('店铺币种')}<input required pattern="[A-Z]{3}" maxLength={3} value={brief.currency} onChange={e=>setBrief({...brief,currency:e.target.value.toUpperCase()})}/></label></div>
      <label>{ui('目标受众')}<textarea maxLength={4000} value={brief.audience||''} onChange={e=>setBrief({...brief,audience:e.target.value})}/></label>
      <label>{ui('风格要求')}<textarea maxLength={4000} value={brief.style||''} onChange={e=>setBrief({...brief,style:e.target.value})}/></label>
      {([{key:'shipping',label:'运输政策'},{key:'returns',label:'退货政策'},{key:'privacy',label:'隐私政策'}] as const).map(item=><label key={item.key}>{ui(item.label)}<textarea maxLength={10000} value={String(brief.merchant_supplied_policies?.[item.key]||'')} onChange={e=>setBrief({...brief,merchant_supplied_policies:{...brief.merchant_supplied_policies,[item.key]:e.target.value}})}/></label>)}
      <button className="primary" disabled={busy||!brief.brand_name.trim()}>{ui('保存品牌资料')}</button>{error&&<p className="error" role="alert">{uiFeedback(error)}</p>}</form></section>;
}
