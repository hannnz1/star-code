import {useEffect,useState,type Dispatch,type SetStateAction} from 'react';
function readDraft<T>(key:string,initial:T):T {
  try {const raw=sessionStorage.getItem('crew-draft:'+key);if(raw!==null){const parsed:unknown=JSON.parse(raw);
    if(typeof parsed===typeof initial&&parsed!==null&&Array.isArray(parsed)===Array.isArray(initial)) {
      if(typeof initial==='object'&&!Array.isArray(initial)&&Object.entries(initial as object).some(([field,value])=>typeof (parsed as Record<string,unknown>)[field]!==typeof value))return initial;
      return parsed as T;
    }}}
  catch { /* Storage may be disabled, corrupt or full. */ }
  return initial;
}
// Scoped local drafts never grant execution permissions. A new key loads a new draft.
export function useSessionDraft<T>(key:string,initial:T):[T,Dispatch<SetStateAction<T>>] {
  const [stored,setStored]=useState(()=>({key,value:readDraft(key,initial)}));
  const value=stored.key===key?stored.value:readDraft(key,initial);
  useEffect(()=>{
    if(stored.key!==key)setStored({key,value});
    try{sessionStorage.setItem('crew-draft:'+key,JSON.stringify(value));}catch{}
  },[key,value,stored.key]);
  const setValue:Dispatch<SetStateAction<T>>=next=>setStored(previous=>{
    const current=previous.key===key?previous.value:readDraft(key,initial);
    return {key,value:typeof next==='function'?(next as (v:T)=>T)(current):next};
  });
  return [value,setValue];
}
