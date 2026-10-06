import {DesignProposal} from './DesignProposal';
import {useEffect,useState} from 'react';
import {ui,uiFeedback} from '../../i18n';
import type {StoreProject,StoreDesignDocument,ProjectMedia} from '../../api.generated';
type DesignSection = StoreDesignDocument['home_sections'][number];
import type {Api} from '../api';
import {useDesignDraft} from './useDesignDraft';
import {useProjectMedia} from '../useProjectMedia';
import './editor.css';
const labels:Record<string,string>={hero:'首屏宣传',categories:'分类入口',products:'推荐商品',story:'品牌介绍',faq:'常见问题'};
export function StoreEditor({api,project}:{api:Api;project:StoreProject}){
  const draft=useDesignDraft(api,project),[selected,setSelected]=useState('hero'),[width,setWidth]=useState('desktop'),[images,setImages]=useState<Record<string,string>>({});
  const media=useProjectMedia(api,project.id);
  useEffect(()=>{let live=true;setImages({});for(const item of media){api<{data_url:string}>(`/commerce/projects/${project.id}/design-media/${item.id}`).then(result=>{if(live)setImages(old=>({...old,[item.id]:result.data_url}));}).catch(()=>{});}return()=>{live=false;};},[api,project.id,media]);
  const doc=draft.document,section=doc?.home_sections.find(s=>s.id===selected);
  function patch(value:Partial<DesignSection>){if(doc&&section)draft.change({...doc,home_sections:doc.home_sections.map(s=>s.id===selected?{...s,...value}:s)});}
  function move(id:string,delta:number){if(!doc)return;const list=[...doc.home_sections],i=list.findIndex(s=>s.id===id),j=i+delta;if(j<0||j>=list.length)return;[list[i],list[j]]=[list[j],list[i]];draft.change({...doc,home_sections:list});}
  return <section className="commerce-card crew-store-editor" data-testid="store-editor"><header className="crew-editor-toolbar"><div><h2>{ui('网站编辑')}</h2><span role="status">{draft.busy?ui('正在保存…'):draft.dirty?ui('有未保存的修改'):ui('已保存草稿')}</span></div>
    <div className="crew-editor-actions"><select aria-label={ui('预览设备')} value={width} onChange={e=>setWidth(e.target.value)}><option value="desktop">{ui('桌面')}</option><option value="tablet">{ui('平板')}</option><option value="mobile">{ui('手机')}</option></select>
    <button disabled={!draft.canUndo||draft.busy} onClick={draft.undo}>{ui('撤销')}</button><button disabled={!draft.canRedo||draft.busy} onClick={draft.redo}>{ui('重做')}</button>
    <button disabled={!draft.dirty||draft.busy} onClick={draft.reset}>{ui('放弃修改')}</button><button className="primary" disabled={!draft.dirty||draft.busy} onClick={()=>void draft.save()}>{ui('保存网站草稿')}</button></div></header>
    <p>{ui('结构预览用于检查布局和内容；真实网站效果以 WordPress 预览和验证为准。')}</p>
    {draft.error&&<div><p role="alert" className="error">{uiFeedback(draft.error)}</p><button disabled={draft.busy} onClick={()=>{if(!draft.dirty||window.confirm(ui('放弃当前输入并读取服务器版本？')))void draft.reload();}}>{ui('重新读取已保存版本')}</button>{doc&&<button onClick={()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='crew-design-draft.json';link.click();URL.revokeObjectURL(url);}}>{ui('导出当前输入')}</button>}<button disabled={draft.busy||draft.dirty} onClick={()=>void draft.initialize()}>{ui('准备或更新编辑草稿')}</button></div>}
    {(!doc||doc.project_revision!==project.revision)&&<button disabled={draft.busy} onClick={()=>void draft.initialize()}>{ui('准备或更新编辑草稿')}</button>}
    {doc&&<div className="crew-editor-layout"><aside className="crew-editor-tree"><h3>{ui('页面区块')}</h3>
      {doc.home_sections.map((s,i)=><div key={s.id} className={s.id===selected?'selected':''}><button aria-pressed={s.id===selected} onClick={()=>setSelected(s.id)}>{ui(labels[s.kind])}{!s.enabled?' · '+ui('隐藏'):''}</button><div><button aria-label={`${ui('上移')} ${i+1}`} disabled={i===0||draft.busy} onClick={()=>move(s.id,-1)}>↑</button><button aria-label={`${ui('下移')} ${i+1}`} disabled={i===doc.home_sections.length-1||draft.busy} onClick={()=>move(s.id,1)}>↓</button></div></div>)}
      <select aria-label={ui('添加区块')} value="" disabled={doc.home_sections.length>=20||draft.busy} onChange={e=>{const kind=e.target.value as DesignSection['kind'];if(!kind)return;const id=crypto.randomUUID();draft.change({...doc,home_sections:[...doc.home_sections,{id,kind,enabled:true,props:{title:ui(labels[kind]),text:'',button_label:'',link:'/shop/',media_id:null,alt:'',items:[]}}]});setSelected(id);}}><option value="">{ui('添加区块')}</option>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{ui(v)}</option>)}</select>
      <h3>{ui('全站样式')}</h3>{(['background','text','accent'] as const).map(k=><label key={k}>{ui(k==='background'?'背景色':k==='text'?'文字颜色':'强调色')}<input type="color" value={doc.theme_tokens?.[k]} onChange={e=>draft.change({...doc,theme_tokens:{...doc.theme_tokens!,[k]:e.target.value}})}/></label>)}
      <select aria-label={ui('字体')} value={doc.theme_tokens?.font} onChange={e=>draft.change({...doc,theme_tokens:{...doc.theme_tokens!,font:e.target.value as 'sans'|'serif'}})}><option value="sans">{ui('无衬线')}</option><option value="serif">{ui('衬线')}</option></select>
    </aside><main className={`crew-design-canvas ${width}`} style={{background:doc.theme_tokens?.background,color:doc.theme_tokens?.text,fontFamily:doc.theme_tokens?.font==='serif'?'Georgia,serif':'inherit'}}><div className="crew-canvas-brand">{project.brief.brand_name}</div>
      {doc.home_sections.filter(s=>s.enabled).map(s=><section key={s.id} className={`crew-canvas-section ${s.kind} ${selected===s.id?'selected':''}`} tabIndex={0} role="button" aria-label={ui('选择区块')+' '+s.props.title} onClick={()=>setSelected(s.id)} onKeyDown={e=>{if(e.key==='Enter')setSelected(s.id);}}>
        {s.props.media_id&&(images[s.props.media_id]?<img src={images[s.props.media_id]} alt={s.props.alt||''}/>:<p>{ui('图片暂不可用')}</p>)}
        <h2>{s.props.title}</h2><p>{s.props.text}</p>{s.kind==='products'&&<p className="crew-canvas-placeholder">{ui('商品将在真实店铺中按商品数据展示')}</p>}
        {!!s.props.items?.length&&<ul>{s.props.items.map((item,i)=><li key={i}>{item}</li>)}</ul>}{s.props.button_label&&<span className="crew-canvas-cta" style={{background:doc.theme_tokens?.accent}}>{s.props.button_label}</span>}
      </section>)}{!doc.home_sections.length&&<p>{ui('添加区块开始编辑首页')}</p>}</main>
    <aside className="crew-editor-inspector"><h3>{ui('区块设置')}</h3>{section?<fieldset disabled={draft.busy}>
      <label>{ui('标题')}<input aria-label={ui('区块标题')} maxLength={160} value={section.props.title} onChange={e=>patch({props:{...section.props,title:e.target.value}})}/></label>
      <label>{ui('正文')}<textarea aria-label={ui('区块正文')} maxLength={4000} value={section.props.text} onChange={e=>patch({props:{...section.props,text:e.target.value}})}/></label>
      <label>{ui('按钮文字')}<input value={section.props.button_label} maxLength={80} onChange={e=>patch({props:{...section.props,button_label:e.target.value}})}/></label>
      <label>{ui('按钮路径')}<input value={section.props.link} onChange={e=>patch({props:{...section.props,link:e.target.value}})}/></label>
      <label>{ui('图片')}<select aria-label={ui('区块图片')} value={section.props.media_id||''} onChange={e=>patch({props:{...section.props,media_id:e.target.value||null}})}><option value="">{ui('无图片')}</option>{media.map(m=><option key={m.id} value={m.id}>{m.image.name}</option>)}</select></label>
      <label>{ui('图片说明')}<input maxLength={200} value={section.props.alt} onChange={e=>patch({props:{...section.props,alt:e.target.value}})}/></label>
      <label>{ui('列表内容，每行一项')}<textarea value={section.props.items?.join('\n')||''} onChange={e=>patch({props:{...section.props,items:e.target.value.split('\n').filter(Boolean)}})}/></label>
      <label><input type="checkbox" checked={section.enabled} onChange={e=>patch({enabled:e.target.checked})}/>{ui('显示区块')}</label>
      <button onClick={()=>{draft.change({...doc,home_sections:doc.home_sections.filter(s=>s.id!==selected)});setSelected('');}}>{ui('删除区块')}</button>
    </fieldset>:<p>{ui('请选择一个区块')}</p>}{section&&<DesignProposal key={project.id+':'+section.id} api={api} project={project} document={doc} section={section} dirty={draft.dirty} onAccepted={draft.replaceSaved}/>}</aside></div>}
  </section>;
}
