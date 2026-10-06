export type CommerceSection = 'overview' | 'website' | 'products' | 'team' | 'settings';
export function allowCrewNavigation() {
  return window.dispatchEvent(new Event('crew-before-navigate',{cancelable:true}));
}
export function readCrewRoute() {
  const match = window.location.hash.match(/^#crew\/(overview|website|products|team|settings|developer)\/([^?]*)(?:\?task=([^&]*))?$/);
  let projectId = '', taskId = ''; 
  try { projectId = decodeURIComponent(match?.[2] || ''); taskId=decodeURIComponent(match?.[3]||''); } catch { /* Invalid URLs open the overview. */ }
  const creating = projectId === '~new';
  if(creating)projectId='';
  return {creating, taskId, section: (match?.[1] || 'overview') as CommerceSection | 'developer', projectId};
}
