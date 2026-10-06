import {useEffect,useRef,useState} from 'react';
import {ui,uiFeedback} from '../i18n';
import type {Api} from './api';
import {useProjectMedia} from './useProjectMedia';
import type {StoreProject,ImportedProducts,ProductDraft,ProjectMedia} from '../api.generated';
export function ProductEditor({api,project,imports,onSaved}:{api:Api;project:StoreProject;imports:ImportedProducts[];onSaved:(value:ImportedProducts)=>void}){
 const empty=():ProductDraft=>({sku:'',title:'',description:'',price:'0.00',currency:project.brief.currency,stock:0,category:'',media_refs:[]});
 const [draft,setDraft]=useState<ProductDraft>(empty),[source,setSource]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loaded,setLoaded]=useState('');
 const pending=useRef<{body:string;id:string}|null>(null),scope=useRef(project.id+':'+project.revision),generation=useRef(0);
 if(scope.current!==project.id+':'+project.revision){scope.current=project.id+':'+project.revision;generation.current++;}
 useEffect(()=>()=>{generation.current++;},[]);
 const media=useProjectMedia(api,project.id);
 useEffect(()=>{setDraft(empty());setSource('');setError('');setNotice('');setBusy(false);pending.current=null;const key=project.id+':'+project.revision;try{const stored=JSON.parse(localStorage.getItem('crew-product-draft:'+key)||'null');if(stored?.draft&&typeof stored.draft.sku==='string'&&stored.draft.currency===project.brief.currency){setDraft(stored.draft);setSource(typeof stored.source==='string'?stored.source:'');}}catch{/* storage unavailable */}setLoaded(key);},[api,project.id,project.revision]);
 useEffect(()=>{const key=project.id+':'+project.revision;if(loaded!==key)return;try{localStorage.setItem('crew-product-draft:'+key,JSON.stringify({draft,source}));}catch{/* form remains usable */}},[draft,source,loaded,project.id,project.revision]);
 function select(value:string){if(busy)return;setSource(value);setNotice('');setError('');if(!value){setDraft(empty());return;}const [id,index]=value.split(':');const item=imports.find(i=>i.id===id)?.result.drafts?.[Number(index)];if(item)setDraft(structuredClone(item));}
 async function save(){if(busy)return;const id=project.id,start=generation.current;setBusy(true);setError('');setNotice('');const payload={expected_project_revision:project.revision,source_import_id:source?source.split(':')[0]:null,draft},body=JSON.stringify(payload);if(pending.current?.body!==body)pending.current={body,id:crypto.randomUUID()};
 try{const result=await api<ImportedProducts>(`/commerce/projects/${id}/product-draft`,{method:'POST',body:JSON.stringify({...payload,client_request_id:pending.current.id})});if(generation.current!==start)return;onSaved(result);setSource(result.id+':0');setNotice('商品草稿已保存，尚未上架');pending.current=null;}
 catch(e){if(generation.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(generation.current===start)setBusy(false);}}
 return <section className="commerce-card" data-testid="product-editor"><h2>{ui('编辑商品')}</h2><p>{ui('保存为新版本商品资料，随后通过团队任务准备上新。')}</p>
 <label>{ui('选择商品草稿')}<select disabled={busy} value={source} onChange={e=>select(e.target.value)}><option value="">{ui('新建商品')}</option>{imports.filter(i=>i.project_revision===project.revision).flatMap(i=>i.result.drafts?.map((d,n)=><option key={i.id+':'+n} value={i.id+':'+n}>{d.title} · {d.sku} · {i.id.slice(0,6)}</option>)||[])}</select></label>
 <form onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={busy} className="crew-product-form">
 {(['sku','title','category'] as const).map(key=><label key={key}>{ui(key==='sku'?'SKU':key==='title'?'商品名称':'分类')}<input required={key!=='category'} aria-label={ui(key==='sku'?'SKU':key==='title'?'商品名称':'分类')} maxLength={key==='title'?200:100} value={draft[key]||''} onChange={e=>setDraft({...draft,[key]:e.target.value})}/></label>)}
 <label>{ui('价格')} ({draft.currency})<input aria-label={ui('商品价格')} type="number" min="0" step="0.01" required value={draft.price} onChange={e=>setDraft({...draft,price:e.target.value})}/></label>
 <label>{ui('库存')}<input aria-label={ui('商品库存')} type="number" min="0" step="1" required value={draft.stock} onChange={e=>setDraft({...draft,stock:Number(e.target.value)})}/></label>
 <label>{ui('描述')}<textarea value={draft.description||''} maxLength={20000} onChange={e=>setDraft({...draft,description:e.target.value})}/></label>
 <label>{ui('选择商品图片')}<select aria-label={ui('选择商品图片')} multiple value={draft.media_refs||[]} onChange={e=>setDraft({...draft,media_refs:Array.from(e.target.selectedOptions).map(o=>o.value)})}>{media.map(m=><option key={m.id} value={m.id}>{m.image.name}</option>)}</select></label>
 <button className="primary" type="submit">{busy?ui('正在保存…'):ui('保存商品草稿')}</button></fieldset></form>
 {error&&<p role="alert" className="error">{uiFeedback(error)}</p>}{notice&&<p role="status">{ui(notice)}</p>}</section>;
}
