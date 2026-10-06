import {ui, uiFeedback} from '../i18n';
import {useCallback, useEffect, useRef, useState} from 'react';
import type {CodeDisposition, CommercePlan, CommercePlanArchive, CommercePlanLabel, CommerceTaskDraft, ImportedProducts, RestoredThemeSource, RestoredThemeSummary, StoreContext, StoreProject, TaskView} from '../api.generated';
import type {Api} from './api';
import {ContentProposal} from './ContentProposal';
import {planNeedsAttention, planNextAction, TaskBoard} from './TaskBoard';
import {ReviewWorkspace} from './ReviewWorkspace';
import {WorkspaceDialog} from './WorkspaceDialog';
import {navigateTabs} from './tabs';
import {FollowUps} from './FollowUps';
import {LocalApplyAutomation} from './LocalApplyAutomation';
import {useSessionDraft} from './useSessionDraft';

const roles: Record<string, string> = {store_manager: '店长', product_content: '商品内容', site_developer: '网站开发'};
const states: Record<string, string> = {PLANNING: '准备中', PENDING: '待执行', RUNNING: '执行中', BUILDING: '制作中',
  VERIFYING: '验证中', REVIEW_REQUIRED: '待审查', APPROVED: '已批准', PUBLISHING: '发布中',
  SUCCEEDED: '已完成', FAILED: '失败', CANCELLED: '已取消', BLOCKED: '受阻',
  NEEDS_INPUT: '待补资料', NEEDS_RECONCILIATION: '待核对', PARTIAL: '部分完成', STALE: '资料已过期'};
export type TeamOpenRequest = {id:string; connection?:boolean; kind?:'build_site'|'launch_products'; draft?:CommerceTaskDraft; planId?:string; tab?:'progress'|'review'|'next'};
type TaskInputs = {title: string; prompt: string; kind: 'build_site' | 'launch_products'; limit: string;
  importId: string; themeSourceId: string; dependencyIds: string[]};

function emptyInputs():TaskInputs {return {title:'',prompt:'',kind:'build_site',limit:'20',importId:'',themeSourceId:'',dependencyIds:[]};}

export function StoreTeam({api, project, imports, onChanged, onPlansChanged, onOpenTask, active=true, openRequest}: {
  active?:boolean; openRequest?:TeamOpenRequest|null;
  api: Api; project: StoreProject; imports: ImportedProducts[]; onChanged: (project: StoreProject) => void;
  onPlansChanged?: (plans: CommercePlan[]) => void; onOpenTask?: (taskId: string) => void;
}) {
  const [context, setContext] = useState<StoreContext | null>(null), [plans, setPlans] = useState<CommercePlan[]>([]);
  const [drafts, setDrafts] = useState<CommerceTaskDraft[]>([]), [draftTitle, setDraftTitle] = useState('');
  const [labels, setLabels] = useState<CommercePlanLabel[]>([]);
  const [archives, setArchives] = useState<CommercePlanArchive[]>([]);
  const [dispositions, setDispositions] = useState<CodeDisposition[]>([]);
  const [connection, setConnection] = useState(''), [prompt, setPrompt] = useState(''), [limit, setLimit] = useState('20');
  const [kind, setKind] = useState<'build_site' | 'launch_products'>('build_site'), [importId, setImportId] = useState('');
  const [busy, setBusy] = useState(false), [connectionError, setConnectionError] = useState(''), [teamError, setTeamError] = useState('');
  const [contentNotice, setContentNotice] = useState('');
  const [panel, setPanel] = useState<'compose' | 'detail' | 'connection' | null>(null);
  const [detailTab, setDetailTab] = useState<'progress' | 'review' | 'next'>('progress');
  const [newInputDraft,setNewInputDraft]=useSessionDraft<TaskInputs>(`team-form:${project.id}:${project.revision}`,emptyInputs());
  const unsaved = useRef<TaskInputs | null>(newInputDraft);
  const inputRevision=useRef(project.revision);
  const localDraftInputs = useRef<Record<string, TaskInputs>>({});
  const [dependencyIds, setDependencyIds] = useState<string[]>([]);
  const [capacity, setCapacity] = useState<{active: number; limit: number; queued: number} | null>(null);
  const batchPending = useRef<{key: string; id: string} | null>(null);
  const autoPending = useRef<{key: string; id: string} | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const formRef = useRef<HTMLElement | null>(null);
  const draftPending = useRef<{key: string; id: string} | null>(null);
  const pending = useRef<{key: string; id: string} | null>(null);
  const [themeSources, setThemeSources] = useState<RestoredThemeSummary[]>([]), [themeSourceId, setThemeSourceId] = useState('');
  useEffect(() => {onPlansChanged?.(plans);}, [plans, onPlansChanged]);
  const live = useRef(true);
  useEffect(() => {
    let active = true; live.current = true;
    if(inputRevision.current!==project.revision){inputRevision.current=project.revision;unsaved.current=newInputDraft;setPanel(value=>value==='compose'?null:value);}
    setContext(null); setPlans([]); setDrafts([]); setLabels([]); setArchives([]); setThemeSources([]); setThemeSourceId('');
    api<StoreContext>(`/commerce/projects/${project.id}/context`).then(value => {if (active) setContext(value);}).catch(() => {});
    setCapacity(null); setDependencyIds([]);
    setDispositions([]);
    api<CodeDisposition[]>(`/commerce/projects/${project.id}/code-dispositions`).then(values => {if (active) setDispositions(values);}).catch(() => {});
    api<{active: number; limit: number; queued: number}>(`/commerce/projects/${project.id}/task-capacity`).then(value => {if (active) setCapacity(value);}).catch(() => {});
    api<CommercePlan[]>(`/commerce/projects/${project.id}/plans`).then(value => {if (active) setPlans(value.filter(p => !!p.steps?.length));})
      .catch(e => {if (active) setTeamError(e.message);});
    api<CommerceTaskDraft[]>(`/commerce/projects/${project.id}/task-drafts`).then(value => {if (active) setDrafts(value);})
      .catch(e => {if (active) setTeamError(e.message);});
    api<CommercePlanLabel[]>(`/commerce/projects/${project.id}/plan-labels`).then(value => {if (active) setLabels(value);})
      .catch(e => {if (active) setTeamError(e.message);});
    api<CommercePlanArchive[]>(`/commerce/projects/${project.id}/plan-archives`).then(value => {if (active) setArchives(value);})
      .catch(e => {if (active) setTeamError(e.message);});
    api<RestoredThemeSummary[]>(`/commerce/projects/${project.id}/restored-themes`).then(value => {if (active) setThemeSources(value);})
      .catch(e => {if (active) setTeamError(e.message);});
    return () => {active = false; live.current = false;};
  }, [api, project.id, project.revision]);
  useEffect(() => {
    const started = drafts.find(item => item.id === selectedDraftId && item.status === 'STARTED');
    if (started?.plan_id) {
      delete localDraftInputs.current[started.id];
      setSelectedDraftId(null); setSelectedPlanId(started.plan_id);
      setPanel(current => current === 'compose' ? 'detail' : current); setDetailTab('progress');
    }
  }, [drafts, selectedDraftId]);
  const hasActivePlans = plans.some(plan => ['PLANNING', 'BUILDING', 'VERIFYING', 'PUBLISHING'].includes(plan.state || ''));
  useEffect(() => {
    if (!hasActivePlans && !drafts.some(draft => draft.status === 'QUEUED')) return;
    let active = true;
    const timer = window.setInterval(() => {
      void api<CommercePlan[]>(`/commerce/projects/${project.id}/plans`).then(values => {
        if (active) setPlans(values.filter(value => !!value.steps?.length));
      }).catch(() => {});
      void api<CommerceTaskDraft[]>(`/commerce/projects/${project.id}/task-drafts`).then(values => {if (active) setDrafts(values);}).catch(() => {});
      void api<CodeDisposition[]>(`/commerce/projects/${project.id}/code-dispositions`).then(values => {if (active) setDispositions(values);}).catch(() => {});
      void api<{active: number; limit: number; queued: number}>(`/commerce/projects/${project.id}/task-capacity`).then(value => {if (active) setCapacity(value);}).catch(() => {});
    }, 5000);
    return () => {active = false; window.clearInterval(timer);};
  }, [api, project.id, hasActivePlans, drafts.some(draft => draft.status === 'QUEUED')]);
  async function connectionAction(bind: boolean) {
    if (busy) return;
    setBusy(true); setConnectionError('');
    try {
      if (bind) {
        const payload = {connection_id: connection, expected_revision: project.revision}, key = JSON.stringify(payload);
        if (pending.current?.key !== key) pending.current = {key, id: crypto.randomUUID()};
        const value = await api<StoreProject>(`/commerce/projects/${project.id}/connections`, {method: 'POST',
          body: JSON.stringify({...payload, client_request_id: pending.current.id})});
        pending.current = null; onChanged(value);
      } else {
        const value = await api<StoreContext>(`/commerce/projects/${project.id}/refresh-context`, {method: 'POST',
          body: JSON.stringify({environment: 'staging', expected_revision: project.revision})});
        setContext(value);
        onChanged(await api<StoreProject>(`/commerce/projects/${project.id}`));
      }
    } catch (e) {setConnectionError(e instanceof Error ? e.message : '店铺连接未完成');}
    finally {setBusy(false);}
  }
  async function start() {
    if (busy) return;
    setBusy(true); setTeamError('');
    const payload = {kind, prompt, expected_revision: project.revision, max_requests: Number(limit),
      import_id: importId || null, theme_source_id: themeSourceId || null}, key = JSON.stringify(payload);
    if (pending.current?.key !== key) pending.current = {key, id: crypto.randomUUID()};
    try {
      const value = await api<CommercePlan>(`/commerce/projects/${project.id}/workflows`, {method: 'POST',
        body: JSON.stringify({...payload, client_request_id: pending.current.id})});
      setPlans(old => [...old.filter(p => p.id !== value.id), value]); setSelectedDraftId(null); setSelectedPlanId(value.id); pending.current = null;
      unsaved.current = null; setNewInputDraft(emptyInputs()); setPanel('detail'); setDetailTab('progress');
    } catch (e) {setTeamError(e instanceof Error ? e.message : '团队任务未创建');}
    finally {setBusy(false);}
  }
  async function downloadTheme() {
    if (busy || !themeSourceId) return;
    setBusy(true); setTeamError('');
    try {
      const source = await api<RestoredThemeSource>(`/commerce/projects/${project.id}/restored-themes/${themeSourceId}`);
      if (!live.current) return;
      const bytes = Uint8Array.from(atob(source.archive_base64), c => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], {type: 'application/zip'})), link = document.createElement('a');
      link.href = url; link.download = 'muse-restored-theme.zip'; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {if (live.current) setTeamError(e instanceof Error ? e.message : '主题代码读取未完成');}
    finally {if (live.current) setBusy(false);}
  }
  async function control(plan: CommercePlan, action: 'advance' | 'resume') {
    if (busy) return;
    setBusy(true); setTeamError('');
    try {
      const value = await api<CommercePlan>(`/commerce/projects/${project.id}/plans/${plan.id}/${action}`, {method: 'POST',
        body: JSON.stringify({expected_revision: plan.revision})});
      setPlans(old => old.map(p => p.id === value.id ? value : p));
    } catch (e) {setTeamError(e instanceof Error ? e.message : '状态未更新');}
    finally {setBusy(false);}
  }
  const updatePlan = useCallback((value: CommercePlan) => {
    setPlans(previous => previous.map(item => item.id === value.id && item.revision !== value.revision ? value : item));
  }, []);
  async function saveDraft() {
    if (busy || !prompt.trim()) return;
    setBusy(true); setTeamError('');
    const title = draftTitle.trim() || (kind === 'build_site' ? '搭建独立站' : '新品上线');
    const payload = {kind, title, prompt, max_requests: Number(limit), import_id: importId || null,
      theme_source_id: themeSourceId || null, dependency_plan_ids: dependencyIds, expected_project_revision: project.revision};
    const selected = drafts.find(draft => draft.id === selectedDraftId);
    try {
      let value: CommerceTaskDraft;
      if (selected?.status === 'DRAFT') {
        value = await api<CommerceTaskDraft>(`/commerce/projects/${project.id}/task-drafts/${selected.id}`, {
          method: 'PUT', body: JSON.stringify({...payload, expected_revision: selected.revision})});
      } else {
        const key = JSON.stringify(payload);
        if (draftPending.current?.key !== key) draftPending.current = {key, id: crypto.randomUUID()};
        value = await api<CommerceTaskDraft>(`/commerce/projects/${project.id}/task-drafts`, {
          method: 'POST', body: JSON.stringify({...payload, client_request_id: draftPending.current.id})});
        draftPending.current = null;
      }
      setDrafts(old => [...old.filter(draft => draft.id !== value.id), value]); setDraftTitle(value.title);
      setSelectedDraftId(value.id); setSelectedPlanId(null);
      if (!selected) {unsaved.current = null;setNewInputDraft(emptyInputs());}
      delete localDraftInputs.current[value.id];
    } catch (e) {setTeamError(e instanceof Error ? e.message : '草稿保存未完成');}
    finally {setBusy(false);}
  }
  async function draftAction(draft: CommerceTaskDraft, action: 'start' | 'archive' | 'restore' | 'rename') {
    if (busy) return;
    setBusy(true); setTeamError('');
    try {
      const body = {expected_revision: draft.revision,
        ...(action === 'start' ? {expected_project_revision: draft.project_revision} : {}),
        ...(action === 'rename' ? {title: draftTitle.trim()} : {})};
      const value = await api<CommerceTaskDraft>(`/commerce/projects/${project.id}/task-drafts/${draft.id}/${action}`,
        {method: 'POST', body: JSON.stringify(body)});
      setDrafts(old => old.map(item => item.id === value.id ? value : item));
      if (action === 'start' && value.plan_id) {
        const created = await api<CommercePlan>(`/commerce/projects/${project.id}/plans/${value.plan_id}`);
        setPlans(old => [...old.filter(item => item.id !== created.id), created]);
        setSelectedDraftId(null); setSelectedPlanId(created.id);
        setPanel('detail'); setDetailTab('progress');
      }
    } catch (e) {setTeamError(e instanceof Error ? e.message : '草稿操作未完成');}
    finally {setBusy(false);}
  }
  async function bulkArchiveDrafts(ids: string[]) {
    return batchDrafts(ids, 'archive');
  }
  async function batchDrafts(ids: string[], action: 'start' | 'archive' | 'cancel', autoApply = false) {
    if (busy || !ids.length) return;
    if (action === 'start' && !window.confirm(ui('确认启动 {0} 份已保存草稿？等待条件满足后会自动进入模型队列并消耗额度。未保存的表单修改不包含在内。{1}', [ids.length, autoApply ? ui('封存后还会一次性自动应用本地成果，基线变化时阻塞，不批准店铺发布。') : '']))) return;
    setBusy(true); setTeamError('');
    const payload = {action, auto_apply_local: autoApply, expected_project_revision: project.revision,
      items: ids.map(id => ({draft_id: id, expected_revision: drafts.find(draft => draft.id === id)!.revision}))};
    const key = JSON.stringify(payload);
    if (batchPending.current?.key !== key) batchPending.current = {key, id: crypto.randomUUID()};
    try {
      const values = await api<CommerceTaskDraft[]>(`/commerce/projects/${project.id}/task-drafts/batch`, {
        method: 'POST', body: JSON.stringify({...payload, client_request_id: batchPending.current.id})});
      batchPending.current = null;
      setDrafts(previous => [...previous.filter(item => !values.some(value => value.id === item.id)), ...values]);
      const loaded = await api<CommercePlan[]>(`/commerce/projects/${project.id}/plans`);
      setPlans(loaded.filter(plan => !!plan.steps?.length));
    } catch (e) {setTeamError(e instanceof Error ? e.message : '批次未完成，请刷新核对；版本冲突时整批拒绝。');}
    finally {setBusy(false);}
  }
  async function armPlan(id: string) {
    const plan = plans.find(item => item.id === id);
    if (!plan || busy || !window.confirm(ui("这一次自动应用该任务的本地静态主题成果？授权有效期 24 小时，基线变化或冲突将阻塞，不批准店铺发布。"))) return;
    setBusy(true); setTeamError('');
    try {
      const current = await api<{code_base_revision: number}>(`/commerce/projects/${project.id}/task-capacity`);
      const payload = {expected_plan_revision: plan.revision, expected_project_revision: project.revision, expected_head_revision: current.code_base_revision};
      const key = JSON.stringify([id, payload]);
      if (autoPending.current?.key !== key) autoPending.current = {key, id: crypto.randomUUID()};
      await api(`/commerce/projects/${project.id}/plans/${id}/local-apply-automation`, {method: 'POST', body: JSON.stringify({...payload, client_request_id: autoPending.current.id})});
      autoPending.current = null; openPlan(id); setContentNotice('一次性本地应用已授权，可在详情中撤销。');
    } catch (e) {setTeamError(e instanceof Error ? e.message : '授权未确认，请刷新核对');}
    finally {setBusy(false);}
  }
  async function refreshBoard() {
    if (busy) return;
    setBusy(true); setTeamError('');
    try {
      const [values, savedDrafts, savedLabels, savedArchives, savedDispositions] = await Promise.all([
        api<CommercePlan[]>(`/commerce/projects/${project.id}/plans`),
        api<CommerceTaskDraft[]>(`/commerce/projects/${project.id}/task-drafts`),
        api<CommercePlanLabel[]>(`/commerce/projects/${project.id}/plan-labels`),
        api<CommercePlanArchive[]>(`/commerce/projects/${project.id}/plan-archives`),
        api<CodeDisposition[]>(`/commerce/projects/${project.id}/code-dispositions`)]);
      if (live.current) {setPlans(values.filter(value => !!value.steps?.length)); setDrafts(savedDrafts); setLabels(savedLabels); setArchives(savedArchives); setDispositions(savedDispositions);}
    } catch (e) {if (live.current) setTeamError(e instanceof Error ? e.message : '看板刷新未完成');}
    finally {if (live.current) setBusy(false);}
  }
  async function renamePlan(plan: CommercePlan) {
    if (busy || !draftTitle.trim()) return;
    setBusy(true); setTeamError('');
    const current = labels.find(label => label.plan_id === plan.id);
    try {
      const value = await api<CommercePlanLabel>(`/commerce/projects/${project.id}/plans/${plan.id}/rename`, {
        method: 'POST', body: JSON.stringify({title: draftTitle.trim(), expected_revision: current?.revision || 0})});
      setLabels(old => [...old.filter(label => label.plan_id !== value.plan_id), value]);
    } catch (e) {setTeamError(e instanceof Error ? e.message : '任务重命名未完成');}
    finally {setBusy(false);}
  }
  async function archivePlans(ids: string[], archived: boolean) {
    if (busy || !ids.length) return;
    setBusy(true); setTeamError('');
    try {
      const items = ids.map(id => ({plan_id: id, expected_plan_revision: plans.find(plan => plan.id === id)!.revision,
        expected_revision: archives.find(item => item.plan_id === id)?.revision || 0}));
      const values = await api<CommercePlanArchive[]>(`/commerce/projects/${project.id}/plan-archives`, {
        method: 'POST', body: JSON.stringify({items, archived})});
      setArchives(previous => [...previous.filter(item => !ids.includes(item.plan_id)), ...values]);
    } catch (e) {setTeamError(e instanceof Error ? e.message : '任务历史有变化，请刷新后重新选择；本批次未修改。');}
    finally {setBusy(false);}
  }
  async function cancelPlan(plan: CommercePlan) {
    const managerId = plan.steps?.find(step => step.role === 'store_manager')?.task_id;
    if (busy || !managerId || !window.confirm(ui("取消此团队任务？已发送的远端操作仍需核对，取消不会撤销它们。"))) return;
    setBusy(true); setTeamError('');
    try {
      const task = await api<TaskView>(`/tasks/${managerId}`);
      await api<TaskView>(`/tasks/${managerId}/cancel`, {method: 'POST',
        body: JSON.stringify({expected_revision: task.revision, content: ''})});
      const updated = await api<CommercePlan>(`/commerce/projects/${project.id}/plans/${plan.id}/advance`, {
        method: 'POST', body: JSON.stringify({expected_revision: plan.revision})});
      setPlans(old => old.map(item => item.id === updated.id ? updated : item));
    } catch (e) {setTeamError(e instanceof Error ? e.message : '取消结果未确认，请刷新并核对');}
    finally {setBusy(false);}
  }
  const validImports = imports.filter(record => record.project_revision === project.revision && record.result.drafts?.length);
  const selectedDraft = drafts.find(draft => draft.id === selectedDraftId);
  const draftDirty = !!selectedDraft && (selectedDraft.kind !== kind || selectedDraft.title !== draftTitle.trim()
    || selectedDraft.prompt !== prompt.trim() || selectedDraft.max_requests !== Number(limit)
    || (selectedDraft.import_id || '') !== importId || (selectedDraft.theme_source_id || '') !== themeSourceId
    || JSON.stringify([...(selectedDraft.dependency_plan_ids || [])].sort()) !== JSON.stringify([...dependencyIds].sort()));
  const selectedPlan = selectedDraft ? null : plans.find(plan => plan.id === selectedPlanId);
  const plan = selectedPlan;
  const currentLabel = plan && labels.find(label => label.plan_id === plan.id);
  function rememberInputs() {
    if (panel !== 'compose') return;
    const value = {title: draftTitle, prompt, kind, limit, importId, themeSourceId, dependencyIds};
    if (selectedDraft) localDraftInputs.current[selectedDraft.id] = value;
    else unsaved.current = value;
  }
  function openPlan(id: string, tab: 'progress' | 'review' | 'next' = 'progress') {
    rememberInputs();
    setSelectedDraftId(null); setSelectedPlanId(id);
    setDraftTitle(labels.find(label => label.plan_id === id)?.title || drafts.find(draft => draft.plan_id === id)?.title || '');
    setPanel('detail'); setDetailTab(tab);
  }
  function openDraft(id: string) {
    const draft = drafts.find(item => item.id === id);
    if (!draft) return;
    rememberInputs();
    const value = localDraftInputs.current[id];
    setSelectedPlanId(null); setSelectedDraftId(id); setKind(value?.kind || draft.kind); setDraftTitle(value?.title ?? draft.title);
    setPrompt(value?.prompt ?? draft.prompt); setLimit(value?.limit || String(draft.max_requests)); setImportId(value?.importId ?? draft.import_id ?? '');
    setThemeSourceId(value?.themeSourceId ?? draft.theme_source_id ?? '');
    setDependencyIds(value?.dependencyIds || draft.dependency_plan_ids || []);
    setPanel('compose');
  }
  function newTask() {
    rememberInputs();
    setSelectedPlanId(''); setSelectedDraftId(null);
    setDraftTitle(unsaved.current?.title || ''); setPrompt(unsaved.current?.prompt || '');
    setKind(unsaved.current?.kind || 'build_site'); setLimit(unsaved.current?.limit || '20');
    setImportId(unsaved.current?.importId || ''); setThemeSourceId(unsaved.current?.themeSourceId || '');
    setDependencyIds(unsaved.current?.dependencyIds || []); setPanel('compose');
  }
  function closePanel() {
    if (busy) return;
    rememberInputs();
    setPanel(null);
  }
  useEffect(()=>{
    if(panel==='compose' && !selectedDraftId && inputRevision.current===project.revision) {
      const value={title:draftTitle,prompt,kind,limit,importId,themeSourceId,dependencyIds};
      unsaved.current=value;setNewInputDraft(value);
    }
  },[panel,selectedDraftId,draftTitle,prompt,kind,limit,importId,themeSourceId,dependencyIds,project.revision]);
  const handledRequest = useRef('');
  useEffect(() => {
    if(!active || !openRequest || handledRequest.current === openRequest.id)return;
    if(openRequest.connection){setPanel('connection');handledRequest.current=openRequest.id;}
    else if(openRequest.planId) {
      if(!plans.some(p=>p.id===openRequest.planId))return;
      openPlan(openRequest.planId,openRequest.tab);handledRequest.current=openRequest.id;
    } else if(openRequest.draft) {
      const draft=openRequest.draft;
      setDrafts(old=>[...old.filter(d=>d.id!==draft.id),draft]);rememberInputs();
      setSelectedPlanId(null);setSelectedDraftId(draft.id);setDraftTitle(draft.title);setPrompt(draft.prompt);
      setKind(draft.kind);setLimit(String(draft.max_requests));setImportId(draft.import_id||'');setThemeSourceId(draft.theme_source_id||'');setDependencyIds(draft.dependency_plan_ids||[]);setPanel('compose');
      handledRequest.current=openRequest.id;
    } else {newTask();setKind(openRequest.kind||'build_site');handledRequest.current=openRequest.id;}
  },[active,openRequest,plans]);
  return <>
    <TaskBoard plans={plans} drafts={drafts} labels={labels} archives={archives} dispositions={dispositions} selectedId={selectedDraft?.id || selectedPlan?.id || null}
      onSelectPlan={openPlan} onSelectDraft={openDraft} onNewTask={newTask} onRefresh={() => void refreshBoard()}
      onBulkArchiveDrafts={bulkArchiveDrafts} onBulkStartDrafts={(ids, auto) => batchDrafts(ids, 'start', auto)} onAutoApplyPlan={id => void armPlan(id)} onCancelQueued={id => void batchDrafts([id], 'cancel')} onArchivePlans={archivePlans}
      onCancelPlan={id => {const value = plans.find(plan => plan.id === id); if (value) void cancelPlan(value);}} refreshing={busy}/>
    <div className="commerce-board-context"><span>{context ? ui('店铺已连接') : ui('尚未连接店铺')}
      {capacity && <> · {ui('运行 {0} / {1} · 排队 {2}', [capacity.active, capacity.limit, capacity.queued])}</>}</span>
      <button onClick={() => setPanel('connection')}>{ui('店铺连接')}</button></div>
    {teamError && panel === null && <p role="alert" className="error commerce-error">{uiFeedback(teamError)}</p>}
    {plans.some(item => item.state === 'SUCCEEDED') && <div className="commerce-next-banner"><div><b>{ui('任务完成后，继续下一步')}</b>
      <p>{ui('查看基于成果的建议，先审查计划，再保存到草稿。')}</p></div><button onClick={() => openPlan(plans.filter(item => item.state === 'SUCCEEDED').at(-1)!.id, 'next')}>{ui('查看下一步建议')}</button></div>}
    <WorkspaceDialog open={active && panel === 'connection'} title={ui('店铺连接')} onClose={closePanel} busy={busy}>
    <section className="commerce-card commerce-connection"><h2>{ui("店铺连接与上下文")}</h2>
      <p>{ui("填写连接服务中已登记的连接 ID。WordPress 凭据由连接服务保管；当前仅允许读取店铺上下文。")}</p>
      <label>{ui("连接 ID")}<input value={connection} onChange={e => setConnection(e.target.value)} placeholder={ui("例如 staging-store")}/></label>
      <button disabled={busy || !/^[a-zA-Z0-9_-]{1,100}$/.test(connection)} onClick={() => void connectionAction(true)}>{ui("绑定店铺连接")}</button>
      <button disabled={busy || !project.environment_refs?.some(ref => ref.environment === 'staging')} onClick={() => void connectionAction(false)}>{ui("刷新店铺上下文")}</button>
      {connectionError && <p role="alert" className="error commerce-error">{uiFeedback(connectionError)}</p>}
      {context ? <article className="commerce-import"><h3>{ui("已保存店铺上下文")}</h3>
        <p>{context.snapshot.pages?.length || 0}{ui("个页面 ·")}{context.snapshot.products?.length || 0}{ui("件商品 ·")}{context.snapshot.environment}</p>
        <p>WordPress {context.capabilities.wordpress_version} · WooCommerce {context.capabilities.woocommerce_version}</p>
        <p>{ui("快照哈希：")}<code>{context.snapshot_hash}</code></p><p>{ui("客户和订单信息不包含在此上下文中。")}</p>
      </article> : <p>{ui("请先连接 staging 店铺并刷新上下文；无已验证连接时不会创建团队任务。")}</p>}
    </section></WorkspaceDialog>
    <WorkspaceDialog open={active && panel === 'compose'} title={ui(selectedDraft ? '编辑商家任务' : '新建商家任务')}
      subtitle={ui('先保存计划，准备好后再启动团队。')} onClose={closePanel} busy={busy}>
    <section ref={formRef} className="commerce-card commerce-team"><h2>{ui("三角色任务准备")}</h2>
      <p>{ui("店长协调网站开发和商品内容，使用当前模型配置。启动后会进入原任务队列并消耗 API 额度；请求上限由整个团队共享，费用取决于模型和 Token。")}</p>
      {capacity && <p role="status">{ui("团队执行容量：")}{capacity.active}/{capacity.limit}{ui(" · 排队 ")}{capacity.queued}{ui("项")}</p>}
      <fieldset disabled={busy || selectedDraft?.status === 'QUEUED'}><legend>{ui("前置计划（批量启动时等待其业务完成）")}</legend>
        {plans.filter(item => item.id !== selectedDraft?.plan_id).map(item => <label key={item.id}>
          <input type="checkbox" checked={dependencyIds.includes(item.id)} onChange={event => setDependencyIds(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))}/>
          {labels.find(label => label.plan_id === item.id)?.title || item.id.slice(0, 8)} · {ui(states[item.state || ''] || item.state)}</label>)}
      </fieldset>
      <p>{ui("网站开发可以编辑并封存主题代码，商品内容负责资料与文案。执行完成后仍需验证和明确批准发布。")}</p>
      {selectedDraft && <p role="status">{ui("正在编辑：")}{selectedDraft.title} · {selectedDraft.status === 'ARCHIVED' ? ui("已归档，先恢复") : ui("草稿")}</p>}
      {selectedDraft?.source_plan_id && <p>{ui("后续任务来源：计划 ")}{selectedDraft.source_plan_id.slice(0, 8)}{ui(" · 版本 ")}{selectedDraft.source_plan_revision}{ui("。这是成果来源记录，不会自动启动前后任务。")}</p>}
      {selectedDraft && <section className="commerce-draft-outline"><h3>{ui("预计执行步骤")}</h3><ol>{selectedDraft.proposed_steps?.map(step => <li key={step}>{ui(step)}</li>)}</ol>
        <p>{ui("这是固定流程说明。启动时仍会重新校验资料与店铺上下文。")}{selectedDraft.theme_source_id ? ui("使用已选主题代码起点。") : ui("默认代码基线版本：{0}；基线更新后请保存草稿再启动。", [selectedDraft.code_base_revision || 0])}</p></section>}
      <label>{ui("任务标题")}<input value={draftTitle} onChange={e => setDraftTitle(e.target.value)} maxLength={160} placeholder={ui("例如：完成品牌独立站首页")}/></label>
      <label>{ui("工作流")}<select value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="build_site">{ui("建站准备")}</option><option value="launch_products">{ui("新品上线准备")}</option></select></label>
      {!!themeSources.length && <><label>{ui("主题代码起点")}<select aria-label={ui("主题代码起点")} value={themeSourceId} disabled={busy} onChange={e => setThemeSourceId(e.target.value)}>
        <option value="">{ui("沿用项目代码基线，没有时生成初始主题")}</option>{themeSources.map(source => <option key={source.id} value={source.id}>{ui("已保存主题 · ")}{source.package.code_revision.slice(0, 10)} · {source.id.slice(0, 8)}
        </option>)}
      </select></label><p>{ui("选择代码起点后，网站开发会沿用其静态文件。主题仍需本次店铺验证和发布审查。")}</p>
        <button disabled={busy || !themeSourceId} onClick={() => void downloadTheme()}>{ui("下载恢复的主题代码")}</button></>}
      <label>{kind === 'launch_products' ? ui("已校验商品批次") : ui("建站商品批次（可选）")}<select aria-label={kind === 'launch_products' ? ui("已校验商品批次") : ui("建站商品批次（可选）")}
        value={importId} onChange={e => setImportId(e.target.value)}>
        <option value="">{kind === 'launch_products' ? ui("请选择当前项目版本的批次") : ui("先建站，稍后再添加商品")}</option>{validImports.map(record => <option key={record.id} value={record.id}>{record.result.drafts?.length}{ui("件商品 ·")}{record.id.slice(0, 10)}</option>)}
      </select></label>
      <label>{ui("团队任务目标")}<textarea aria-label={ui("团队任务目标")} value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={10000} placeholder={ui("说明本次建站或新品准备目标")}/></label>
      <label>{ui("共享模型请求上限")}<input type="number" min="1" max="100" value={limit} onChange={e => setLimit(e.target.value)}/></label>
      <button disabled={busy || selectedDraft?.status === 'ARCHIVED' || selectedDraft?.status === 'QUEUED' || !prompt.trim() || !Number.isInteger(Number(limit)) || Number(limit) < 1 || Number(limit) > 100} onClick={() => void saveDraft()}>{selectedDraft?.status === 'DRAFT' ? ui("保存草稿修改") : ui("保存任务草稿")}</button>
      {selectedDraft ? <>
        {selectedDraft.status === 'QUEUED' && <><p>{ui("等待：")}{selectedDraft.queue_reason}{ui("。取消排队后恢复草稿，重新核对资料。")}</p><button disabled={busy} onClick={() => void batchDrafts([selectedDraft.id], 'cancel')}>{ui("取消排队")}</button></>}
        {selectedDraft.status === 'DRAFT' && <><button className="primary" disabled={busy || !context || draftDirty || selectedDraft.project_revision !== project.revision} onClick={() => void draftAction(selectedDraft, 'start')}>{ui("启动这份草稿")}</button>
          <button disabled={busy || draftDirty || selectedDraft.project_revision !== project.revision} onClick={() => void batchDrafts([selectedDraft.id], 'start')}>{ui("加入后台队列")}</button>
          <button disabled={busy} onClick={() => void draftAction(selectedDraft, 'archive')}>{ui("归档草稿")}</button></>}
        {selectedDraft.status === 'ARCHIVED' && <button disabled={busy} onClick={() => void draftAction(selectedDraft, 'restore')}>{ui("恢复草稿")}</button>}
        {selectedDraft.project_revision !== project.revision && <p>{ui("项目资料已更新。恢复草稿后请保存修改，再启动新版本。")}</p>}
      </> : <button className="primary" disabled={busy || !context || !prompt.trim() || !Number.isInteger(Number(limit)) || Number(limit) < 1 || Number(limit) > 100 || ((kind === 'launch_products' || !!importId) && !validImports.some(r => r.id === importId))} onClick={() => void start()}>{ui("启动三角色准备任务")}</button>}
      {selectedDraft && draftDirty && <p>{ui("草稿有未保存修改。先保存，再启动。")}</p>}
      {selectedDraft && <button disabled={busy} onClick={newTask}>{ui("新建另一项任务")}</button>}
      {teamError && <p role="alert" className="error commerce-error">{uiFeedback(teamError)}</p>}
      {contentNotice && <p role="status">{uiFeedback(contentNotice)}</p>}
    </section></WorkspaceDialog>
    <WorkspaceDialog open={active && panel === 'detail' && !!plan} title={ui('任务详情')}
      subtitle={currentLabel?.title || (plan?.kind === 'build_site' ? ui('搭建独立站') : ui('新品上线'))} onClose={closePanel} busy={busy} wide>
      {plan && <article ref={detailRef} key={plan.id} data-plan-id={plan.id} className="commerce-plan-detail"><h3>{plan.kind === 'build_site' ? ui("建站准备") : ui("新品准备")} · {ui(states[plan.state || ''] || plan.state)}</h3>
        <p data-testid="plan-next-action" className={planNeedsAttention(plan) ? 'commerce-plan-attention-action' : 'commerce-plan-next-action'}>{ui("下一步：")}{planNextAction(plan)}</p>
        <details className="crew-technical-details"><summary>{ui("技术明细与版本")}</summary><p>{ui("计划编号 ")}{plan.id.slice(0, 8)}{ui(" · 计划版本 ")}{plan.revision}{ui(" · 项目版本 ")}{project.revision}</p></details>
        <section className="crew-task-outcome"><h4>{ui("完成情况")}</h4><p>{ui("已完成 {0} / {1} 个角色步骤",[(plan.steps||[]).filter(s=>s.status==='SUCCEEDED').length,(plan.steps||[]).length])}</p><p>{ui("需要你决定：")}{planNextAction(plan)}</p>{plan.error_code&&<p role="status">{ui("仍需处理：")}{plan.error_code}</p>}</section>
        <div className="commerce-detail-tabs" role="tablist" aria-label={ui('任务详情内容')} onKeyDown={navigateTabs}>
          {([{id: 'progress', title: '任务进度'}, {id: 'review', title: '成果审查'}, {id: 'next', title: '后续任务'}] as const).map(item =>
            <button key={item.id} role="tab" tabIndex={detailTab === item.id ? 0 : -1} aria-selected={detailTab === item.id} id={`task-tab-${item.id}`} aria-controls={`task-panel-${item.id}`}
              onClick={() => setDetailTab(item.id)}>{ui(item.title)}</button>)}
        </div>
        {teamError && <p role="alert" className="error commerce-error">{uiFeedback(teamError)}</p>}
        {contentNotice && <p role="status">{uiFeedback(contentNotice)}</p>}
        <div role="tabpanel" id="task-panel-progress" aria-labelledby="task-tab-progress" hidden={detailTab !== 'progress'}>
        {archives.find(item => item.plan_id === plan.id)?.archived && <p role="status">{ui("任务已归档，成果与审查记录仍保留。")}</p>}
        {['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE'].includes(plan.state || '') &&
          <button disabled={busy} onClick={() => void archivePlans([plan.id], !archives.find(item => item.plan_id === plan.id)?.archived)}>
            {archives.find(item => item.plan_id === plan.id)?.archived ? ui("恢复此任务") : ui("归档此任务")}</button>}
        <label>{ui("任务显示标题")}<input aria-label={ui("任务显示标题")} value={draftTitle} maxLength={160} onChange={e => setDraftTitle(e.target.value)} placeholder={plan.kind === 'build_site' ? ui("搭建独立站") : ui("新品上线")}/></label>
        <button disabled={busy || !draftTitle.trim() || draftTitle.trim() === currentLabel?.title} onClick={() => void renamePlan(plan)}>{ui("重命名任务")}</button>
        <h4>{ui("团队依赖关系")}</h4>
        <ul className="commerce-dependency-list">{plan.steps?.map(step => <li key={step.id}><b>{ui(ui(roles[step.role]) || step.role)}</b> · {ui(states[step.status || ''] || step.status)}<br/>
          <small>{step.dependencies?.length ? ui("前置：{0}", [step.dependencies.map(id => ui(roles[plan.steps?.find(item => item.id === id)?.role || '']) || '未知步骤').join('、')]) : ui("协调入口：核对目标后委派角色")}</small><br/>
          {step.status === 'PENDING' && step.dependencies?.some(id => plan.steps?.find(item => item.id === id)?.status !== 'SUCCEEDED') &&
            <small>{ui("排队中：等待前置角色完成")}</small>}
          {step.task_id ? <>{onOpenTask ? <button type="button" className="commerce-task-link" onClick={() => onOpenTask(step.task_id!)}>{ui("打开执行日志与审批 · ")}{step.task_id.slice(0, 8)}</button> : <code>{step.task_id}</code>}</> : ui("尚未委派")}{step.output_hash && <p>{ui("成果哈希：")}<code>{step.output_hash}</code></p>}</li>)}</ul>
        {plan.error_code && <p>{ui("阻塞原因：")}{plan.error_code}</p>}
        {plan.state === 'NEEDS_INPUT' && plan.error_code === 'FACTS_INCOMPLETE' && !!plan.products?.length &&
          <ContentProposal key={`${plan.id}:${plan.revision}`} api={api} projectId={project.id} planId={plan.id} onConfirmed={updated => {
            setContentNotice('文案已确认，请使用新批次重新创建团队任务。'); onChanged(updated);
          }}/>} 
        {Array.isArray(plan.blueprint?.required_settings?.missing_fields) && !!plan.blueprint.required_settings.missing_fields.length &&
          <p>{ui("待补充：")}{plan.blueprint.required_settings.missing_fields.map(String).join('、')}{ui("。资料确认后重新创建计划。")}</p>}
        <p>{ui("执行日志和技术审批可在对应角色任务中查看。团队成果还需店铺验证及商家发布审查。")}</p>
        <LocalApplyAutomation key={`auto:${project.id}:${plan.id}`} api={api} plan={plan}/>
        <button disabled={busy} onClick={() => void control(plan, 'advance')}>{ui("刷新团队状态")}</button>
        </div>
        <div role="tabpanel" id="task-panel-review" aria-labelledby="task-tab-review" hidden={detailTab !== 'review'}>
          <ReviewWorkspace key={`${project.id}:${plan.id}:${plan.revision}`} api={api} plan={plan} onPlan={updatePlan} active={active && panel === 'detail' && detailTab === 'review'}/>
        </div>
        <div role="tabpanel" id="task-panel-next" aria-labelledby="task-tab-next" hidden={detailTab !== 'next'}>
        <FollowUps key={`follow-ups:${project.id}:${plan.id}`} api={api} plan={plan} active={active && panel === 'detail' && detailTab === 'next'}
          onDrafts={values => setDrafts(previous => [...previous.filter(item => !values.some(value => value.id === item.id)), ...values])} onDraft={draft => {
          setDrafts(previous => [...previous.filter(item => item.id !== draft.id), draft]);
          setSelectedPlanId(''); setSelectedDraftId(draft.id); setKind(draft.kind); setDraftTitle(draft.title);
          setPrompt(draft.prompt); setLimit(String(draft.max_requests)); setImportId(draft.import_id || '');
          setThemeSourceId(draft.theme_source_id || '');
          setDependencyIds(draft.dependency_plan_ids || []);
          setPanel('compose');
        }}/>
        </div>
        {['PLANNING', 'BUILDING', 'BLOCKED'].includes(plan.state || '') && plan.steps?.some(step => step.role === 'store_manager' && step.task_id) &&
          <button disabled={busy} onClick={() => void cancelPlan(plan)}>{ui("取消团队任务")}</button>}
        {plan.state === 'BLOCKED' && plan.error_code === 'MODEL_UNAVAILABLE' && <button disabled={busy} onClick={() => void control(plan, 'resume')}>{ui("恢复原任务")}</button>}
      </article>}
    </WorkspaceDialog>
  </>;
}
