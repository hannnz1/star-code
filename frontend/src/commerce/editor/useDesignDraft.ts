import {useEffect,useRef,useState} from 'react';
import type {Api} from '../api';
import type {StoreDesignDocument,StoreProject} from '../../api.generated';
import {ui} from '../../i18n';

export function useDesignDraft(api:Api,project:StoreProject) {
  const [document,setDocument]=useState<StoreDesignDocument|null>(null),[saved,setSaved]=useState<StoreDesignDocument|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[undo,setUndo]=useState<StoreDesignDocument[]>([]),[redo,setRedo]=useState<StoreDesignDocument[]>([]);
  const scope=project.id+':'+project.revision,active=useRef(scope);active.current=scope;
  const pending=useRef<{body:string;id:string}|null>(null);
  const dirty=!!document&&JSON.stringify(document)!==JSON.stringify(saved);
  useEffect(()=>{let live=true;setDocument(null);setSaved(null);setUndo([]);setRedo([]);setError('');setBusy(true);pending.current=null;
    api<StoreDesignDocument|null>(`/commerce/projects/${project.id}/design`).then(doc=>{if(live){setDocument(doc);setSaved(doc);}}).catch(e=>{if(live)setError(e.message);}).finally(()=>{if(live)setBusy(false);});
    return()=>{live=false;};},[api,scope]);
  useEffect(()=>{if(!dirty)return;const handler=(e:BeforeUnloadEvent)=>{e.preventDefault();};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[dirty]);
  useEffect(()=>{if(!dirty)return;const handler=(e:Event)=>{
    if(!window.confirm(ui('放弃当前输入并读取服务器版本？')))e.preventDefault();
    else {setDocument(saved);setUndo([]);setRedo([]);setError('');}
  };window.addEventListener('crew-before-navigate',handler);return()=>window.removeEventListener('crew-before-navigate',handler);},[dirty,saved]);
  function change(next:StoreDesignDocument){if(!document||busy)return;setUndo(old=>[...old.slice(-49),document]);setRedo([]);setDocument(next);setError('');}
  async function initialize(){if(busy)return;setBusy(true);const start=scope;try{const doc=await api<StoreDesignDocument>(`/commerce/projects/${project.id}/design`,{method:'POST',body:JSON.stringify({expected_project_revision:project.revision})});if(active.current===start){setDocument(doc);setSaved(doc);setError('');}}catch(e){if(active.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(active.current===start)setBusy(false);}}
  async function save(){if(!document||busy)return;const start=scope;setBusy(true);setError('');const body=JSON.stringify(document);if(pending.current?.body!==body)pending.current={body,id:crypto.randomUUID()};
    try{const doc=await api<StoreDesignDocument>(`/commerce/projects/${project.id}/design`,{method:'PATCH',body:JSON.stringify({expected_project_revision:project.revision,expected_revision:document.revision,client_request_id:pending.current.id,document})});
      if(active.current===start){setDocument(doc);setSaved(doc);setUndo([]);setRedo([]);pending.current=null;}}
    catch(e){if(active.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(active.current===start)setBusy(false);}}
  async function reload(){if(busy)return;const start=scope;setBusy(true);try{const doc=await api<StoreDesignDocument|null>(`/commerce/projects/${project.id}/design`);if(active.current===start){setDocument(doc);setSaved(doc);setUndo([]);setRedo([]);setError('');pending.current=null;}}catch(e){if(active.current===start)setError(e instanceof Error?e.message:'Error');}finally{if(active.current===start)setBusy(false);}}
  return {replaceSaved:(doc:StoreDesignDocument)=>{
    // Acceptance is already saved on the server. Undo restores content against
    // the accepted version; it must never move the server version backwards.
    const rebase=(old:StoreDesignDocument)=>({...doc,home_sections:old.home_sections,theme_tokens:old.theme_tokens});
    setUndo(old=>document?[...old.slice(-49).map(rebase),rebase(document)]:[]);
    setDocument(doc);setSaved(doc);setRedo([]);pending.current=null;setError('');
  },document,busy,error,dirty,change,save,initialize,reset:()=>{setDocument(saved);setUndo([]);setRedo([]);setError('');},canUndo:!!undo.length,canRedo:!!redo.length,
    reload,
    undo:()=>{if(!busy&&document&&undo.length){setRedo(old=>[...old,document]);setDocument(undo.at(-1)!);setUndo(old=>old.slice(0,-1));}},
    redo:()=>{if(!busy&&document&&redo.length){setUndo(old=>[...old,document]);setDocument(redo.at(-1)!);setRedo(old=>old.slice(0,-1));}}};
}
