import {ui, uiFeedback, LanguageSwitch, useUiLanguage} from './i18n';
import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowUp, ArrowUpRight, BookOpen, Check, ChevronRight, CircleHelp, Code2, Download, FileText, FolderOpen, Globe2, History, LayoutTemplate, Package, Users, Layers3, LoaderCircle, LockKeyhole, Pause, Play, Plus, Search, Settings2, ShieldCheck, Sparkles, Square, Trash2, X } from 'lucide-react';
import './style.css';
import './theme.css';
import {DitherArtwork} from './commerce/DitherArtwork';
const CommerceHome = lazy(() => import('./commerce/CommerceHome').then(module => ({default: module.CommerceHome})));
import {commerceErrorMessage} from './commerce/api';
import type {StoreProject} from './api.generated';
import {allowCrewNavigation, readCrewRoute, type CommerceSection} from './commerce/navigation';

import type {TaskView as Task, WorkspaceView as Workspace, EventView as Event, ArtifactView as Artifact, SourceView as Source, ApprovalView as Approval, MemoryView as Memory, FileChangeView as FileChange, UncertainActionView as UncertainAction} from './api.generated';
const statusNames:Record<string,string> = {QUEUED:'排队中',RUNNING:'进行中',WAITING_INPUT:'等待补充',WAITING_APPROVAL:'等待批准',PAUSED:'已暂停',INTERRUPTED:'需要核对',SUCCEEDED:'已完成',FAILED:'未完成',CANCELLED:'已取消'};
const permissionLabels = {default:'逐次批准写入和执行',acceptEdits:'允许工作区编辑，执行需批准',plan:'只读计划'};
const terminal = new Set(['SUCCEEDED','FAILED','CANCELLED']);
const modeHints:Record<string,{placeholder:string;ability:string}> = {
  general:{placeholder:'你想完成什么？',ability:'根据目标选择工具，按当前权限执行'},
  research:{placeholder:'输入网页链接和你想研究的问题…',ability:'阅读公开网页 · 记录来源 · 生成报告'},
  documents:{placeholder:'描述要整理的文件和期望结果…',ability:'读取文档 · 整理副本 · 保留原文件'},
  coding:{placeholder:'描述要开发或修复的功能…',ability:'阅读代码 · 修改文件 · 运行验证'},
};
const modes = [{id:'general',name:'自由任务',icon:Sparkles,desc:'从一个想法开始'}, {id:'research',name:'网页研究',icon:Globe2,desc:'阅读来源，形成有据可查的报告'}, {id:'documents',name:'资料整理',icon:FileText,desc:'提取、分类，保留每份原件'}, {id:'coding',name:'编程助手',icon:Code2,desc:'理解代码、修改并运行验证'}];
const samples:Record<string,string> = {general:'阅读工作区资料，列出当前项目最需要解决的三个问题，并说明下一步。',research:'阅读这些公开网页，比较关键差异并生成带来源引用的报告：\n',documents:'阅读工作区中的 TXT、Markdown 和文本 PDF，提取要点并生成摘要报告，保留原文件。',coding:'先阅读项目结构，说明入口、主要模块和测试命令，暂时不要修改代码。'};
function Markdown({text}:{text:string}) { return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{a:props=><a {...props} target="_blank" rel="noopener noreferrer"/>,img:props=><span>{ui("[图片：")}{props.alt}]</span>}}>{text}</ReactMarkdown></div>; }

function App() {
  const language = useUiLanguage();
  const initialRoute = useRef(readCrewRoute());
  const acceptedRoute = useRef(window.location.href);
  const [initialHistoryPosition] = useState(()=>{
    const position=window.history.state?.crewPosition;
    if(Number.isSafeInteger(position))return position as number;
    window.history.replaceState({...window.history.state,crewPosition:0},'');return 0;
  });
  const acceptedPosition=useRef(initialHistoryPosition),restoringHistory=useRef(false);
  const [merchantView,setMerchantView] = useState(initialRoute.current.section !== 'developer');
  const [merchantSection,setMerchantSection] = useState<CommerceSection>(initialRoute.current.section === 'developer' ? 'overview' : initialRoute.current.section);
  const [merchantProject,setMerchantProject] = useState(initialRoute.current.projectId);
  const [merchantProjects,setMerchantProjects] = useState<StoreProject[]>([]);
  const merchantContext = useCallback((projects:StoreProject[], projectId:string) => {setMerchantProjects(projects);setMerchantProject(projectId);const project=projects.find(p=>p.id===projectId);if(merchantView&&project){setWorkspace(project.workspace_id);const route=readCrewRoute();if(!route.projectId&&!route.creating){window.history.replaceState(window.history.state,'',`#crew/${route.section}/${encodeURIComponent(projectId)}`);acceptedRoute.current=window.location.href;}}}, [merchantView]);
  function navigate(section:CommerceSection | 'developer', projectId=merchantProject, creating=false) {
    const destination=`#crew/${section}/${encodeURIComponent(creating?'~new':projectId)}`;
    if(window.location.hash===destination)return true;
    if(!allowCrewNavigation())return false;
    window.history.pushState({crewPosition:++acceptedPosition.current},'',destination);
    acceptedRoute.current=window.location.href;
    setMerchantView(section !== 'developer');
    if(section !== 'developer') setMerchantSection(section);
    setMerchantProject(projectId);setSelected(null);return true;
  }
  useEffect(() => {
    const restore = () => {
      if(window.location.href===acceptedRoute.current){restoringHistory.current=false;return;}
      if(restoringHistory.current)return;
      const stored=window.history.state?.crewPosition;
      const position=Number.isSafeInteger(stored)?stored as number:acceptedPosition.current+1;
      if(!Number.isSafeInteger(stored))window.history.replaceState({...window.history.state,crewPosition:position},'');
      if(!allowCrewNavigation()){
        const delta=acceptedPosition.current-position;
        if(delta){restoringHistory.current=true;window.history.go(delta);}
        else window.history.replaceState({...window.history.state,crewPosition:acceptedPosition.current},'',acceptedRoute.current);
        return;
      }
      acceptedPosition.current=position;acceptedRoute.current=window.location.href;
      const route=readCrewRoute();setMerchantView(route.section !== 'developer');if(route.section !== 'developer')setMerchantSection(route.section);setMerchantProject(route.projectId);setSelected(route.taskId||null);
    };
    window.addEventListener('popstate',restore);window.addEventListener('hashchange',restore);return()=>{window.removeEventListener('popstate',restore);window.removeEventListener('hashchange',restore);};
  }, []);
  const [token,setToken] = useState(()=>sessionStorage.getItem('muse-token')||'');
  const [entered,setEntered] = useState(false), [tokenInput,setTokenInput] = useState('');
  const [error,setError] = useState(''), [busy,setBusy] = useState(false);
  const [tasks,setTasks] = useState<Task[]>([]), [workspaces,setWorkspaces] = useState<Workspace[]>([]), [workspace,setWorkspace] = useState('');
  const [selected,setSelected] = useState<string|null>(initialRoute.current.taskId||null), [task,setTask] = useState<Task|null>(null);
  const [events,setEvents] = useState<Event[]>([]), [artifacts,setArtifacts] = useState<Artifact[]>([]), [sources,setSources] = useState<Source[]>([]), [approvals,setApprovals] = useState<Approval[]>([]);
  const [prompt,setPrompt] = useState(''), [scenario,setScenario] = useState('general'), [search,setSearch] = useState('');
  const [permissionMode,setPermissionMode] = useState<Task['permission_mode']>('default');
  const [coordinatorMode,setCoordinatorMode] = useState(false);
  const [model,setModel] = useState(''), [tab,setTab] = useState('成果');
  const [modal,setModal] = useState<'memory'|'workspace'|null>(null), [memories,setMemories] = useState<Memory[]>([]);
  const modalRef=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    if(!modal)return;
    const opener=document.activeElement as HTMLElement|null;
    modalRef.current?.showModal();
    const previous=document.body.style.overflow;document.body.style.overflow='hidden';
    return()=>{document.body.style.overflow=previous;if(opener?.isConnected)opener.focus();};
  },[modal]);
  const [memoryCandidates,setMemoryCandidates] = useState<Memory[]>([]);
  const [memoryTitle,setMemoryTitle] = useState(''), [memoryContent,setMemoryContent] = useState(''), [memoryScope,setMemoryScope] = useState('project'), [memoryId,setMemoryId] = useState<string|null>(null);
  const [workspacePath,setWorkspacePath] = useState(''), [workspaceName,setWorkspaceName] = useState('');
  const [reply,setReply] = useState('');
  const [fileHistory,setFileHistory] = useState<FileChange[]>([]);
  const [children,setChildren] = useState<Task[]>([]);
  const [uncertainActions,setUncertainActions] = useState<UncertainAction[]>([]);
  const [reconciliationNotes,setReconciliationNotes] = useState<Record<string,string>>({});
  const cursor = useRef(0), active = useRef<string|null>(null);
  const submission = useRef<{payload:string;id:string}|null>(null);
  const api = useCallback(async <T,>(path:string, init:RequestInit={}):Promise<T> => {
    const response=await fetch('/api'+path,{...init,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...init.headers}});
    if(!response.ok) {if(response.status===401)setEntered(false); const body=await response.json().catch(()=>({})); throw new Error(body.error?commerceErrorMessage(body.error):typeof body.detail==='string'?body.detail:'请求未完成，请检查输入或稍后重试');}
    return response.status===204 ? undefined as T : response.json();
  },[token]);
  const act = async (operation:()=>Promise<void>)=>{setBusy(true);setError('');try{await operation();}catch(e){setError(String(e instanceof Error?e.message:e));}finally{setBusy(false);}};
  const refresh = useCallback(async()=>{
    const [list,spaces,settings]=await Promise.all([api<Task[]>('/tasks'),api<Workspace[]>('/workspaces'),api<{provider?:{model:string}}>('/settings')]);
    setTasks(list);setWorkspaces(spaces);setWorkspace(value=>value||spaces[0]?.id||'');setModel(settings.provider?.model||'');setEntered(true);
  },[api]);
  useEffect(()=>{if(token){sessionStorage.setItem('muse-token',token);refresh().catch(e=>setError(e.message));}},[token,refresh]);
  useEffect(()=>{if(!entered)return;const timer=setInterval(()=>refresh().catch(e=>setError(e.message)),4000);return()=>clearInterval(timer);},[entered,refresh]);
  const refreshTask = useCallback(async(id:string)=>{
    const [detail,files,links,pending,changes,childTasks,uncertain]=await Promise.all([api<Task>('/tasks/'+id),api<Artifact[]>('/tasks/'+id+'/artifacts'),api<Source[]>('/tasks/'+id+'/sources'),api<Approval[]>('/approvals?task_id='+id),api<FileChange[]>('/tasks/'+id+'/file-history'),api<Task[]>('/tasks/'+id+'/children'),api<UncertainAction[]>('/tasks/'+id+'/uncertain-actions')]);
    if(active.current!==id)return;
    setTask(detail);setArtifacts(files);setSources(links);setApprovals(pending.filter(x=>x.status==='PENDING'));setTasks(list=>list.map(t=>t.id===id?detail:t));
    setFileHistory(changes);
    setChildren(childTasks);setUncertainActions(uncertain);
  },[api]);
  useEffect(()=>{
    active.current=selected;setTask(null);setEvents([]);setArtifacts([]);setSources([]);setApprovals([]);setChildren([]);setUncertainActions([]);setReconciliationNotes({});cursor.current=0;setReply('');
    if(!selected||!entered)return;
    const id=selected, controller=new AbortController();let stopped=false;
    const stream=async()=>{
      while(!stopped){
        try{
          await refreshTask(id);
          const response=await fetch(`/api/tasks/${id}/events?after=${cursor.current}`,{headers:{Authorization:'Bearer '+token},signal:controller.signal});
          if(!response.ok||!response.body)throw new Error('事件连接中断，正在重连');
          const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='';
          while(!stopped){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let index:number;
            while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const line=frame.split('\n').find(x=>x.startsWith('data: '));if(!line)continue;
              const event=JSON.parse(line.slice(6)) as Event;
              if(event.sequence>cursor.current&&active.current===id){cursor.current=event.sequence;setEvents(old=>[...old,event]);if(['status','artifact','approval_required','approval_renewed','assistant_message','input_required'].includes(event.type))await refreshTask(id);}
            }
          }
          await refreshTask(id);
        }catch(e){if(!stopped)setError(e instanceof Error?e.message:'连接中断');}
        if(!stopped)await new Promise(resolve=>setTimeout(resolve,1800));
      }
    };void stream();const timer=setInterval(()=>refreshTask(id).catch(()=>{}),2500);
    return()=>{stopped=true;controller.abort();clearInterval(timer);};
  },[selected,entered,token,refreshTask]);
  function openTask(id:string) {if(!allowCrewNavigation())return;window.history.pushState({crewPosition:++acceptedPosition.current},'',`#crew/developer/${encodeURIComponent(merchantProject)}?task=${encodeURIComponent(id)}`);acceptedRoute.current=window.location.href;setMerchantView(false);setSelected(id);}
  const createTask=async(parent?:Task)=>{if(!prompt.trim())return;await act(async()=>{
    const payload={prompt,permission_mode:permissionMode,coordinator_mode:coordinatorMode,scenario:parent?.scenario||scenario,workspace_id:parent?.workspace_id||workspace,parent_task_id:parent?.id||null};
    const key=JSON.stringify(payload);
    if(submission.current?.payload!==key)submission.current={payload:key,id:crypto.randomUUID()};
    const created=await api<Task>('/tasks',{method:'POST',body:JSON.stringify({...payload,client_request_id:submission.current!.id})});
    submission.current=null;
    openTask(created.id);setPrompt('');await refresh();
  });};
  const setPolicy=async(mode:Task['permission_mode'])=>{if(!task)return;const id=task.id;await act(async()=>{const changed=await api<Task>(`/tasks/${id}/policy`,{method:'POST',body:JSON.stringify({expected_revision:task.revision,permission_mode:mode})});if(active.current===id)setTask(changed);await refresh();});};
  const control=async(action:string,content='')=>{if(!task)return;const id=task.id;await act(async()=>{const changed=await api<Task>(`/tasks/${id}/${action}`,{method:'POST',body:JSON.stringify({expected_revision:task.revision,content})});if(active.current===id){setTask(changed);setReply('');}await refresh();});};
  const reconcileExternal=async(item:UncertainAction,successful:boolean)=>act(async()=>{if(!task)return;await api('/external-actions/'+task.id+'/reconcile',{method:'POST',body:JSON.stringify({call_id:item.id,action_digest:item.digest,expected_revision:task.revision,successful,explanation:reconciliationNotes[item.id]||''})});await refreshTask(task.id);});
  const renew=async(item:Approval)=>act(async()=>{await api('/approvals/'+item.id+'/renew',{method:'POST',body:JSON.stringify({action_digest:item.action_digest})});if(task)await refreshTask(task.id);});
  const decide=async(item:Approval,allow:boolean)=>act(async()=>{await api('/approvals/'+item.id+'/decision',{method:'POST',body:JSON.stringify({allow,action_digest:item.action_digest})});if(task)await refreshTask(task.id);});
  const download=async(file:Artifact)=>act(async()=>{const response=await fetch('/api/artifacts/'+file.id,{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw new Error('下载失败');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=file.name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  const openMemory=()=>act(async()=>{setMemories(await api('/memories'));setMemoryCandidates(await api('/memory/candidates'));setModal('memory');});
  const saveMemory=()=>act(async()=>{await api('/memories'+(memoryId?'/'+memoryId:''),{method:memoryId?'PATCH':'POST',body:JSON.stringify({scope:memoryScope,title:memoryTitle,content:memoryContent,workspace_id:memoryScope==='project'?workspace:null})});setMemoryId(null);setMemoryTitle('');setMemoryContent('');setMemories(await api('/memories'));});
  const chosenSpace=workspaces.find(x=>x.id===(task?.workspace_id||workspace));
  const lastThinking=events.reduce((last,e,index)=>e.type==='thinking_summary'?index:last,-1);
  const liveThinking=events.slice(lastThinking+1).filter(e=>e.type==='thinking_summary_delta').map(e=>String(e.payload.text||'')).join('');
  const taskMessages=events.filter(e=>e.type==='assistant_message'&&String(e.payload.text||'').trim());
  const lastAssistant=events.reduce((last,e,index)=>e.type==='assistant_message'?index:last,-1);
  const streaming=events.slice(lastAssistant+1).filter(e=>e.type==='text_delta').map(e=>String(e.payload.text||'')).join('');
  const allDone=task&&terminal.has(task.status);

  if(!entered)return <main className="login"><div className="login-card"><LanguageSwitch/><div className="brand"><span className="brand-icon"><Layers3 size={25}/></span>Crew</div><h1>{ui("你的想法，")}<br/>{ui("从这里开始。")}</h1><p>{ui("研究网页、整理资料、完成编程任务。")}<br/>{ui("连接这台电脑上的 Crew 工作台。")}</p><label htmlFor="token">{ui("本地访问令牌")}</label><input id="token" type="password" autoComplete="off" value={tokenInput} onChange={e=>setTokenInput(e.target.value)} placeholder={ui("从启动窗口复制访问令牌")} onKeyDown={e=>{if(e.key==='Enter')setToken(tokenInput.trim());}}/><button className="primary" onClick={()=>{if(token===tokenInput.trim())void act(refresh);else setToken(tokenInput.trim());}} disabled={!tokenInput.trim()}>{ui("进入工作台")}<ArrowUpRight size={17}/></button>{error&&<p role="alert" className="error">{uiFeedback(error)}</p>}<small><LockKeyhole size={14}/>{ui("这是本机访问令牌，不是模型 API 密钥")}</small></div><div className="login-art"><DitherArtwork className="login-dither"/><span>Your AI commerce team.</span></div></main>;

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-icon"><Layers3 size={21}/></span>Crew<span className="beta">LOCAL</span></div>
      <label className="crew-store-switch">{ui("当前店铺")}<select aria-label={ui("切换店铺")} value={merchantProject} onChange={e=>{if(!navigate('overview',e.target.value,!e.target.value))e.currentTarget.value=merchantProject;}}><option value="">{ui("创建店铺")}</option>{merchantProjects.map(p=><option key={p.id} value={p.id}>{p.brief.brand_name}</option>)}</select></label>
      <div className="nav-label">{ui("工作台")}</div><nav aria-label={ui("主导航")}>
        {([{id:'overview',label:'概览',icon:Layers3},{id:'website',label:'网站',icon:LayoutTemplate},{id:'products',label:'商品',icon:Package},{id:'team',label:'团队任务',icon:Users}] as const).map(item=><button key={item.id} className={'nav-item '+(merchantView&&merchantSection===item.id?'selected':'')} aria-current={merchantView&&merchantSection===item.id?'page':undefined} onClick={()=>navigate(item.id)}><item.icon size={17}/>{ui(item.label)}</button>)}
        <button className={'nav-item '+(!merchantView?'selected':'')} onClick={()=>navigate('developer')}><Code2 size={17}/>{ui("开发空间")}</button>
        <button className={'nav-item '+(merchantView&&merchantSection==='settings'?'selected':'')} onClick={()=>navigate('settings')}><Settings2 size={17}/>{ui("设置")}</button>
      </nav>
      <button className="new-task" onClick={()=>{navigate('developer');setPrompt('');}}><Plus size={17}/>{ui("新建任务")}</button>
      {!merchantView&&<><div className="section-row"><span>{ui("最近任务")}</span><History size={14}/></div><div className="search"><Search size={14}/><input aria-label={ui("搜索任务")} placeholder={ui("搜索任务")} value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="task-list">{tasks.filter(t=>t.prompt.toLowerCase().includes(search.toLowerCase())).map(t=><button key={t.id} className={'task-item '+(selected===t.id?'active':'')} onClick={()=>openTask(t.id)}><span className={'dot '+t.status}/><span>{t.prompt}</span><small>{ui(statusNames[t.status])}</small></button>)}</div></>}
      <div className="sidebar-bottom"><button className="workspace-switch" onClick={()=>setModal('workspace')}><FolderOpen size={18}/><span>{chosenSpace?.name||ui("选择工作区")}<small>{ui("本地文件 · 明确授权")}</small></span></button><div className="model-pill"><span className="dot SUCCEEDED"/><span>{model || ui('未配置')}</span></div></div></aside>
    <main className="main"><header className="topbar"><span>{merchantView?ui("商家工作台"):ui("开发空间")}<ChevronRight size={13}/><b>{merchantView?merchantProjects.find(p=>p.id===merchantProject)?.brief.brand_name||ui("创建店铺"):task?ui("任务详情"):ui("新的开始")}</b></span><div><LanguageSwitch/><span className="local-badge"><span/>{ui("本地运行")}</span><button className="icon-button" aria-label={ui("工作区设置")} onClick={()=>setModal('workspace')}><Settings2 size={18}/></button></div></header>
      {error&&<div className="banner error" role="alert">{uiFeedback(error)}<button aria-label={ui("关闭错误")} onClick={()=>setError('')}><X size={15}/></button></div>}
      <div hidden={!merchantView}><Suspense fallback={<p role="status">{ui("正在加载商家工作台…")}</p>}><CommerceHome api={api} workspaces={workspaces} workspace={workspace} active={merchantView} section={merchantSection} selectedProjectId={merchantProject} onSection={section=>navigate(section)} onContext={merchantContext} onProject={(id,section='overview')=>navigate(section,id,!id)} onMemory={openMemory} onWorkspace={()=>setModal('workspace')} model={model} onOpenTask={openTask}/></Suspense></div>{!merchantView&&(!selected?<div className="home"><div className="eyebrow"><span/>Your AI commerce team.</div><h1>{ui("开发空间")}</h1><div className="crew-developer-workspace" data-testid="developer-workspace"><FolderOpen size={16} aria-hidden="true"/><div><span>{ui("当前工作目录")}</span><code>{workspaces.find(space=>space.id===workspace)?.path||ui("未选择工作区")}</code><small>{ui("可在设置中的工作区管理切换目录。")}</small></div></div><p className="intro">{ui("把目标交给 Crew。从查找资料到完成代码，")}<br/>{ui("让每一步都有进展，让每个结果有据可查。")}</p><section className="composer"><textarea placeholder={ui(modeHints[scenario].placeholder)} aria-label={ui("任务目标")} aria-describedby="crew-mode-ability" value={prompt} onChange={e=>setPrompt(e.target.value)}/><div className="composer-footer"><select aria-label={ui("选择权限模式")} value={permissionMode} onChange={e=>setPermissionMode(e.target.value as Task['permission_mode'])}>{Object.entries(permissionLabels).map(([id,label])=><option key={id} value={id}>{ui(label)}</option>)}</select><label title={ui("让多个 AI 分工完成任务，由主助手汇总和检查结果。")}><input type="checkbox" aria-label={ui("团队协作")} aria-description={ui("让多个 AI 分工完成任务，由主助手汇总和检查结果。")} checked={coordinatorMode} onChange={e=>setCoordinatorMode(e.target.checked)}/>{ui("团队协作")}</label><button className="send" aria-label={ui("开始任务")} disabled={busy||!prompt.trim()||!workspace} onClick={()=>createTask()}><ArrowUp size={18}/><span>{ui("开始任务")}</span></button></div><div className="crew-mode-guidance" data-testid="mode-guidance"><div role="status"><p id="crew-mode-ability">{ui(modeHints[scenario].ability)}</p>{coordinatorMode&&<p>{ui("多个 AI 分工，由主助手汇总检查。")}</p>}</div><div className="crew-mode-guidance-actions"><span>{ui("点击开始后执行")}</span><button type="button" disabled={!!prompt.trim()} title={prompt.trim()?ui("先清空输入，再填入示例"):undefined} onClick={()=>{if(!prompt.trim())setPrompt(ui(samples[scenario]));}}>{ui("填入示例")}</button></div></div></section><div className="mode-row">{modes.map(mode=><button key={mode.id} className={scenario===mode.id?'active':''} aria-pressed={scenario===mode.id} onClick={()=>setScenario(mode.id)}><mode.icon size={15}/>{ui(mode.name)}{scenario===mode.id&&<Check size={14} aria-hidden="true"/>}</button>)}</div><div className="section-row home-section"><span>{ui("从一个具体任务开始")}</span><small>{ui("想法 → 行动 → 成果")}</small></div><div className="starter-grid">{modes.slice(1).map(mode=><button key={mode.id} className="starter" onClick={()=>{setScenario(mode.id);if(!prompt.trim())setPrompt(ui(samples[mode.id]));}}><div><mode.icon size={22} strokeWidth={1.5}/><ArrowUpRight size={16}/></div><h3>{ui(mode.name)}</h3><p>{ui(mode.desc)}</p></button>)}</div><div className="home-note"><ShieldCheck size={15}/><span>{ui("代码命令由你批准。关闭网页后，已启动的后台任务继续运行。")}</span></div></div>:
      <div className="task-layout"><section className="conversation">{task?<><div className="task-heading"><div className="eyebrow">{ui(modes.find(m=>m.id===task.scenario)?.name || '')} · {new Date(task.created_at*1000).toLocaleDateString(language)}</div><div className="heading-row"><h1 title={task.prompt}>{task.prompt.slice(0,75)}</h1><span className={'status '+task.status}>{ui(statusNames[task.status])}</span></div><div className="task-policy"><span>{ui("权限：")}{ui(permissionLabels[task.permission_mode])} · v{task.policy_version}{task.legacy_policy?ui(" · 旧版策略"):''}</span><select aria-label={ui("修改权限模式")} value={task.permission_mode} disabled={busy||task.status==='RUNNING'||terminal.has(task.status)} onChange={e=>setPolicy(e.target.value as Task['permission_mode'])}>{Object.entries(permissionLabels).map(([id,label])=><option key={id} value={id}>{ui(label)}</option>)}</select></div><div className="task-actions">{['QUEUED','RUNNING'].includes(task.status)&&<button disabled={busy} onClick={()=>control('pause')}><Pause size={14}/>{ui("暂停")}</button>}{['PAUSED','INTERRUPTED'].includes(task.status)&&<button disabled={busy} onClick={()=>control('resume')}><Play size={14}/>{ui("继续执行")}</button>}{!terminal.has(task.status)&&<button disabled={busy} onClick={()=>control('cancel')}><Square size={13}/>{ui("取消任务")}</button>}</div></div><div className="user-message"><span>{ui("你的目标")}</span><p>{task.prompt}</p></div><div className="agent-label"><span className="mini-brand"><Layers3 size={15}/></span>Crew<small>{model}</small></div>{liveThinking&&<details open className="message"><summary>{ui("思考摘要")}</summary><Markdown text={liveThinking}/></details>}{taskMessages.map(event=><div className="message" key={event.sequence}><Markdown text={String(event.payload.text)}/></div>)}{streaming&&<div className="message"><Markdown text={streaming}/></div>}{!taskMessages.length&&!streaming&&<div className="waiting"><LoaderCircle size={17} className={task.status==='RUNNING'?'spin':''}/>{task.status==='QUEUED'?ui("任务已加入队列，等待 Worker 领取。"):ui(statusNames[task.status])}</div>}{task.error&&<div className="notice"><CircleHelp size={18}/><p>{task.error}</p></div>}{task.result&&!taskMessages.some(e=>e.payload.text===task.result)&&<Markdown text={task.result}/>}
      {uncertainActions.map(item=><div className="approval" key={item.id}><b>{ui("请核对中断前的操作结果")}</b><p>{ui("确认实际结果后记录结论，再继续任务。此操作不会重新执行命令，也不作为测试通过的凭证。")}</p><code>{item.name}: {JSON.stringify(item.arguments)}</code><textarea aria-label={ui("核对说明 ")+item.id} value={reconciliationNotes[item.id]||''} onChange={e=>setReconciliationNotes(notes=>({...notes,[item.id]:e.target.value}))}/><div><button disabled={busy||!(reconciliationNotes[item.id]||'').trim()} onClick={()=>reconcileExternal(item,false)}>{ui("已确认失败")}</button><button disabled={busy||!(reconciliationNotes[item.id]||'').trim()} onClick={()=>reconcileExternal(item,true)}>{ui("已确认成功")}</button></div></div>)}
      {approvals.map(item=><div className="approval" key={item.id}><div className="approval-title"><ShieldCheck size={20}/><b>{ui("这一步需要你的批准")}</b></div><p>{ui("请审阅工具")}{item.name}{ui("的目标和参数。批准仅授权这一次操作；代码命令拥有当前系统用户的权限。")}</p><code>{String(item.arguments.command||JSON.stringify(item.arguments))}</code><small>{workspaces.find(w=>w.id===item.workspace_id)?.path}<br/>{ui(permissionLabels[item.permission_mode])} · v{item.policy_version}<br/>{ui("批准仅适用于这一次操作 ·")}{new Date(item.expires_at*1000).toLocaleTimeString(language)}{ui("前有效")}</small><div>{item.expires_at*1000<=Date.now()?<button disabled={busy} onClick={()=>renew(item)}>{ui("审批已过期 · 续期后重新审阅")}</button>:<><button disabled={busy} onClick={()=>decide(item,false)}>{ui("拒绝")}</button><button className="primary" disabled={busy} onClick={()=>decide(item,true)}>{ui("批准执行")}<Check size={14}/></button></>}</div></div>)}
      {children.length>0&&<div className="reply-box"><h3>{ui("子任务")}</h3>{children.map(child=><button className="space-item" key={child.id} onClick={()=>{setWorkspace(child.workspace_id);setSelected(child.id);}}><Layers3 size={18}/><span>{child.prompt.slice(0,80)}<small>{ui(statusNames[child.status])} · {workspaces.find(space=>space.id===child.workspace_id)?.name||ui("独立工作区")}</small></span><ChevronRight size={16}/></button>)}</div>}
      {fileHistory.length>0&&<div className="reply-box"><label>{ui("文件变更记录 · 仅回退专用文件工具的修改")}</label>{fileHistory.map(file=><div className="file-change" key={file.call_id}><code>{file.path}</code><small>{file.restored?ui("已回退"):ui("{0} → {1}", [file.before_hash?.slice(0,8)||'新文件', file.after_hash.slice(0,8)])}</small>{!file.restored&&(allDone||task.status==='INTERRUPTED')&&<button disabled={busy} onClick={()=>act(async()=>{await api(`/file-actions/${task.id}/${allDone?'rewind':'reconcile'}`,{method:'POST',body:JSON.stringify({call_id:file.call_id,expected_revision:task.revision})});await refreshTask(task.id);})}>{allDone?ui("回退该文件"):ui("核对写入结果")}</button>}</div>)}</div>}
      {task.status==='WAITING_INPUT'&&<div className="reply-box"><label htmlFor="reply">{ui("补充信息后继续")}</label><textarea id="reply" value={reply} onChange={e=>setReply(e.target.value)}/><button className="primary" disabled={busy||!reply.trim()} onClick={()=>control('input',reply)}>{ui("发送补充信息")}</button></div>}
      {allDone&&<div className="reply-box"><label htmlFor="followup">{ui("在此基础上继续")}</label><textarea id="followup" placeholder={ui("补充一个新目标，将创建关联任务…")} value={prompt} onChange={e=>setPrompt(e.target.value)}/><button className="primary" disabled={busy||!prompt.trim()} onClick={()=>createTask(task)}>{ui("创建跟进任务")}<ArrowUpRight size={15}/></button></div>}</>:<div className="waiting">{ui("正在读取任务…")}</div>}</section>
      <aside className="evidence"><div className="evidence-tabs">{['成果','过程','来源'].map(name=><button key={name} className={tab===name?'active':''} onClick={()=>setTab(name)}>{ui(name)}{name==='成果'&&artifacts.length>0&&<small>{artifacts.length}</small>}</button>)}</div>{tab==='成果'?<div>{artifacts.length?artifacts.map(file=><button className="artifact" key={file.id} onClick={()=>download(file)}><FileText size={24}/><span>{file.name}<small>{ui("版本 ")}{file.version} · SHA256 {file.sha256.slice(0,8)}</small></span><Download size={15}/></button>):<div className="empty-panel"><FileText size={31} strokeWidth={1}/><h3>{ui("成果会出现在这里")}</h3><p>{ui("报告和资料输出将保留版本，")}<br/>{ui("完成后可随时下载。")}</p></div>}</div>:tab==='来源'?<div>{sources.map(source=><a className="source" href={source.url} target="_blank" rel="noopener noreferrer" key={source.id}><Globe2 size={16}/><span>{source.title||source.url}<small>{source.url}</small></span><ArrowUpRight size={14}/></a>)}{!sources.length&&<p className="empty-small">{ui("还没有已读取的网页来源。")}</p>}</div>:<ol className="timeline">{events.filter(e=>!['text_delta','assistant_message','thinking_summary_delta'].includes(e.type)).map(event=><li key={event.sequence}><span className="timeline-point"/><small>#{event.sequence} · {new Date(event.created_at*1000).toLocaleTimeString(language)}</small><b>{event.type==='status'?ui(statusNames[String(event.payload.status)]):event.type==='tool_started'?ui("执行工具"):event.type==='tool_result'?ui("工具结果"):event.type==='tool_prepared'?ui("准备工具"):event.type==='thinking_summary'?ui("思考摘要"):event.type==='approval_required'?ui("等待批准"):event.type==='input_required'?ui("等待补充"):event.type}</b><details><summary>{String(event.payload.name||event.payload.status||ui("查看详情"))}</summary>{event.type==='thinking_summary'?<Markdown text={String(event.payload.text||ui("未返回摘要"))}/>:<pre>{JSON.stringify(event.payload,null,2)}</pre>}</details></li>)}</ol>}{task&&<div className="metrics"><div><span>{ui("模型请求")}</span><b>{task.metrics.model_requests}</b></div><div><span>{ui("工具调用")}</span><b>{task.metrics.tool_calls}</b></div><div><span>{ui("活动时间")}</span><b>{task.metrics.active_seconds.toFixed(1)} s</b></div><div><span>{ui("输入 / 输出 Token")}</span><b>{task.metrics.usage?(task.metrics.usage.complete?'':ui("部分统计："))+`${task.metrics.usage.input_tokens} / ${task.metrics.usage.output_tokens}`:ui("未提供")}</b></div></div>}</aside></div>)}
      <footer>Crew <span>·</span>{ui("让想法成为成果")}</footer></main>
    {modal&&<dialog ref={modalRef} className="crew-settings-dialog" aria-label={modal==='memory'?ui("记忆管理"):ui("工作区管理")} onCancel={e=>{e.preventDefault();setModal(null);}}><section className="modal"><div className="modal-heading"><h2>{modal==='memory'?ui("记忆管理"):ui("工作区管理")}</h2><button className="icon-button" aria-label={ui("关闭弹窗")} onClick={()=>setModal(null)}><X size={19}/></button></div>{modal==='memory'?<><p className="muted">{ui("你决定 Crew 记住什么。删除后，新请求不再使用该记忆。")}</p><div className="memory-list">{memoryCandidates.map(item=><article key={item.id}><div><b>{ui("待确认：")}{item.title}</b><small>{item.conflict_id?ui("与现有记忆冲突"):ui("用户级候选")}</small><p>{item.content}</p></div><button onClick={()=>act(async()=>{await api('/memory/'+item.id+'/confirm',{method:'POST'});setMemories(await api('/memories'));setMemoryCandidates(await api('/memory/candidates'));})}>{ui("确认")}</button><button onClick={()=>act(async()=>{await api('/memory/'+item.id+'/withdraw',{method:'POST'});setMemoryCandidates(await api('/memory/candidates'));})}>{ui("撤回")}</button></article>)}{memories.map(item=><article key={item.id}><div><b>{item.title}</b><small>{item.scope==='user'?ui("用户级"):workspaces.find(w=>w.id===item.workspace_id)?.name||ui("项目级")}</small><p>{item.content}</p></div><button onClick={()=>{setMemoryId(item.id);setMemoryTitle(item.title);setMemoryContent(item.content);setMemoryScope(item.scope);if(item.workspace_id)setWorkspace(item.workspace_id);}}>{ui("编辑")}</button><button className="icon-button" aria-label={ui("删除记忆 ")+item.title} onClick={()=>act(async()=>{await api('/memories/'+item.id,{method:'DELETE'});setMemories(await api('/memories'));})}><Trash2 size={16}/></button></article>)}</div><label>{ui("记忆标题")}<input value={memoryTitle} onChange={e=>setMemoryTitle(e.target.value)}/></label><label>{ui("记忆内容")}<textarea value={memoryContent} onChange={e=>setMemoryContent(e.target.value)}/></label><label>{ui("作用范围")}<select value={memoryScope} onChange={e=>setMemoryScope(e.target.value)}><option value="project">{ui("当前工作区")}</option><option value="user">{ui("所有工作区")}</option></select></label><button className="primary" disabled={busy||!memoryTitle.trim()||!memoryContent.trim()} onClick={saveMemory}>{ui("保存记忆")}</button></>:<><p className="muted">{ui("指定已有的本地文件夹，授权 Crew 在其中完成任务。")}</p>{workspaces.map(space=><button key={space.id} className="space-item" onClick={()=>{setWorkspace(space.id);setModal(null);}}><FolderOpen size={18}/><span>{space.name}<small>{space.path}</small></span>{workspace===space.id&&<Check size={17}/>}</button>)}<label>{ui("工作区名称")}<input value={workspaceName} onChange={e=>setWorkspaceName(e.target.value)}/></label><label>{ui("文件夹绝对路径")}<input placeholder="C:\Projects\my-project" value={workspacePath} onChange={e=>setWorkspacePath(e.target.value)}/></label><button className="primary" disabled={busy||!workspacePath.trim()} onClick={()=>act(async()=>{const space=await api<Workspace>('/workspaces',{method:'POST',body:JSON.stringify({path:workspacePath,name:workspaceName||'工作区'})});setWorkspace(space.id);setWorkspaceName('');setWorkspacePath('');await refresh();setModal(null);})}>{ui("添加工作区")}</button></>}{error&&<p className="error" role="alert">{uiFeedback(error)}</p>}</section></dialog>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
