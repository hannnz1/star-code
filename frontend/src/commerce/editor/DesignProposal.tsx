import {useEffect,useRef,useState} from 'react';
import {ui,uiFeedback} from '../../i18n';
import type {Api} from '../api';
import type {StoreDesignDocument,StoreProject} from '../../api.generated';
type DesignSection = StoreDesignDocument['home_sections'][number];
type Job={id:string;status:string;before:DesignSection['props'];after:DesignSection['props']|null;error_code:string|null;model_requests:number};
export function DesignProposal({api,project,document,section,dirty,onAccepted}:{api:Api;project:StoreProject;document:StoreDesignDocument;section:DesignSection;dirty:boolean;onAccepted:(doc:StoreDesignDocument)=>void}){
 const [instruction,setInstruction]=useState(''),[job,setJob]=useState<Job|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const pending=useRef<{body:string;id:string}|null>(null);
 const scope = project.id+':'+project.revision+':'+section.id;
 const active = useRef<string|null>(scope);active.current=scope;
 const currentInput=useRef({dirty,revision:document.revision});currentInput.current={dirty,revision:document.revision};
 useEffect(()=>()=>{active.current=null;},[]);
 useEffect(()=>{if(!job||!['QUEUED','RUNNING'].includes(job.status))return;let live=true;const timer=setInterval(()=>{api<Job>(`/commerce/projects/${project.id}/design-proposals/${job.id}`).then(value=>{if(live)setJob(value);}).catch(e=>{if(live)setError(e.message);});},1500);return()=>{live=false;clearInterval(timer);};},[api,project.id,job?.id,job?.status]);
 async function generate(){if(busy||dirty)return;const start=scope;setBusy(true);setError('');const payload={expected_project_revision:project.revision,design_revision:document.revision,section_id:section.id,instruction},body=JSON.stringify(payload);if(pending.current?.body!==body)pending.current={body,id:crypto.randomUUID()};try{const result=await api<Job>(`/commerce/projects/${project.id}/design-proposals`,{method:'POST',body:JSON.stringify({...payload,client_request_id:pending.current.id})});if(active.current===start)setJob(result);}catch(e){if(active.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(active.current===start)setBusy(false);}}
 async function control(accept:boolean){if(!job||busy)return;const start=scope;setBusy(true);setError('');try{const result=await api<StoreDesignDocument|Job>(`/commerce/projects/${project.id}/design-proposals/${job.id}/${accept?'accept':'reject'}`,{method:'POST',body:JSON.stringify({expected_design_revision:document.revision})});if(active.current!==start)return;if(accept&&(currentInput.current.dirty||currentInput.current.revision!==document.revision)){setError('RESOURCE_CONFLICT');setJob(null);return;}if(accept)onAccepted(result as StoreDesignDocument);setJob(null);pending.current=null;}catch(e){if(active.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(active.current===start)setBusy(false);}}
 return <section className="crew-design-proposal"><h4>{ui('让 AI 修改此区块')}</h4><p>{ui('先保存草稿，再生成局部建议；接受前可查看差异。')}</p><textarea aria-label={ui('区块修改要求')} value={instruction} maxLength={2000} onChange={e=>setInstruction(e.target.value)}/><button disabled={busy||dirty||!instruction.trim()||!!job&&['QUEUED','RUNNING'].includes(job.status)} onClick={()=>void generate()}>{ui('生成修改建议')}</button>
 {job&&<><p role="status">{ui(job.status==='QUEUED'?'等待后台任务处理':job.status==='RUNNING'?'AI 正在准备建议':job.status==='READY'?'建议待审查':'建议未完成')}</p>{job.after&&<><h5>{ui('修改前')}</h5><p>{job.before.title}</p><p>{job.before.text}</p><h5>{ui('修改后')}</h5><p>{job.after.title}</p><p>{job.after.text}</p><p>{job.before.button_label} → {job.after.button_label}</p></>}
 {job.status==='READY'&&<button disabled={busy||dirty} onClick={()=>void control(true)}>{ui('接受修改')}</button>}<button disabled={busy} onClick={()=>void control(false)}>{ui('拒绝或取消建议')}</button></>}{error&&<p role="alert" className="error">{uiFeedback(error)}</p>}</section>;
}
