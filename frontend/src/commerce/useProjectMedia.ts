import {useEffect,useState} from 'react';
import type {ProjectMedia} from '../api.generated';
import type {Api} from './api';

export function useProjectMedia(api:Api,projectId:string) {
  const [media,setMedia]=useState<ProjectMedia[]>([]);
  useEffect(()=>{
    let live=true,generation=0;setMedia([]);
    async function refresh(){
      const request=++generation;
      try {
        const items=await api<ProjectMedia[]>(`/commerce/projects/${projectId}/media`);
        if(live&&request===generation)setMedia(items);
      }catch{/* A failed refresh retains the last successfully read choices. */}
    }
    const changed=(event:Event)=>{if((event as CustomEvent<string>).detail===projectId)void refresh();};
    window.addEventListener('crew-media-updated',changed);void refresh();
    return()=>{live=false;window.removeEventListener('crew-media-updated',changed);};
  },[api,projectId]);
  return media;
}
