import {ui, useUiLanguage} from '../i18n';
import {useMemo, useState} from 'react';
import {AlertCircle, ArrowRight, MoreHorizontal, Search} from 'lucide-react';
import type {CodeDisposition, CommercePlan, CommercePlanArchive, CommercePlanLabel, CommerceTaskDraft} from '../api.generated';

type Lane = 'draft' | 'active' | 'ready' | 'done';
const lanes: {id: Lane; title: string; description: string}[] = [
  {id: 'draft', title: '草稿', description: '计划好，尚未启动'},
  {id: 'active', title: '进行中', description: '执行、排队或等待问题处理'},
  {id: 'ready', title: '待审查', description: '成果待审查，或已批准待发布'},
  {id: 'done', title: '已结束', description: '已完成、取消或失效'},
];
const stateNames: Record<string, string> = {NEEDS_INPUT: '待补资料', PLANNING: '规划中', BUILDING: '制作中',
  VERIFYING: '验证中', REVIEW_REQUIRED: '待审查', APPROVED: '已批准', PUBLISHING: '发布中',
  SUCCEEDED: '已完成', PARTIAL: '部分完成', NEEDS_RECONCILIATION: '待核对', STALE: '资料失效',
  BLOCKED: '受阻', FAILED: '失败', CANCELLED: '已取消'};

export function planLane(plan: CommercePlan): Lane {
  if (['REVIEW_REQUIRED', 'APPROVED'].includes(plan.state || '')) return 'ready';
  if (['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE'].includes(plan.state || '')) return 'done';
  return 'active';
}

export function planNeedsAttention(plan: CommercePlan): boolean {
  return ['NEEDS_INPUT', 'BLOCKED', 'NEEDS_RECONCILIATION', 'PARTIAL'].includes(plan.state || '');
}

export function planNextAction(plan: CommercePlan): string {
  switch (plan.state) {
    case 'NEEDS_INPUT': return ui('补齐商家资料，再建立新任务');
    case 'REVIEW_REQUIRED': return ui('查看验证与发布审查');
    case 'APPROVED': return ui('已批准，仍需明确执行发布');
    case 'BLOCKED': return ui('查看阻塞原因与恢复方式');
    case 'NEEDS_RECONCILIATION': return ui('只读核对远端结果');
    case 'PARTIAL': return ui('核对已完成与未完成的发布步骤');
    case 'VERIFYING': return ui('查看后台验证进度');
    case 'PUBLISHING': return ui('查看发布回执和进度');
    case 'SUCCEEDED': return ui('查看最终成果');
    case 'FAILED': return ui('查看错误与任务日志');
    case 'CANCELLED': return ui('查看取消记录');
    case 'STALE': return ui('资料已变化，重新建立任务');
    default: return ui('查看团队执行进度');
  }
}

export function TaskBoard({plans, drafts, labels, archives, dispositions = [], selectedId, onSelectPlan, onSelectDraft, onNewTask, onRefresh, refreshing, onBulkArchiveDrafts, onBulkStartDrafts, onAutoApplyPlan, onCancelQueued, onArchivePlans, onCancelPlan}: {
  plans: CommercePlan[]; drafts: CommerceTaskDraft[]; labels: CommercePlanLabel[]; selectedId: string | null;
  archives: CommercePlanArchive[];
  dispositions?: CodeDisposition[];
  onSelectPlan: (id: string, tab?: 'progress' | 'review' | 'next') => void; onSelectDraft: (id: string) => void;
  onNewTask: () => void; onRefresh: () => void; refreshing: boolean;
  onBulkArchiveDrafts?: (ids: string[]) => Promise<void>;
  onBulkStartDrafts?: (ids: string[], autoApply?: boolean) => Promise<void>;
  onAutoApplyPlan?: (id: string) => void;
  onCancelQueued?: (id: string) => void;
  onArchivePlans: (ids: string[], archived: boolean) => Promise<void>;
  onCancelPlan: (id: string) => void;
}) {
  const language = useUiLanguage();
  const [query, setQuery] = useState('');
  const [view,setView]=useState(()=>{try{return localStorage.getItem('crew-board-view')||(window.matchMedia('(max-width: 600px)').matches?'list':'board');}catch{return 'board';}});
  function changeView(value:string){setView(value);try{localStorage.setItem('crew-board-view',value);}catch{}}
  const [kindFilter, setKindFilter] = useState('all');
  const [archiveFilter, setArchiveFilter] = useState('current');
  const [draftFilter, setDraftFilter] = useState('all');
  const [stateFilter, setStateFilter] = useState('all');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedDraftIds, setSelectedDraftIds] = useState<string[]>([]);
  const [selectedPlanIds, setSelectedPlanIds] = useState<string[]>([]);
  const archiveIds = new Set(archives.filter(item => item.archived).map(item => item.plan_id));
  const selectedPlans = selectedPlanIds.filter(id => plans.some(plan => plan.id === id && planLane(plan) === 'done'));
  const activeSelection = selectedDraftIds.filter(id => drafts.some(draft => draft.id === id && draft.status === 'DRAFT'));
  const filtered = useMemo(() => plans.filter(plan => {
    const title = labels.find(label => label.plan_id === plan.id)?.title
      || drafts.find(draft => draft.plan_id === plan.id)?.title || ui(plan.kind === 'build_site' ? '搭建独立站' : '新品上线');
    const text = [plan.id, title, ui(plan.kind === 'build_site' ? '建站' : '新品上线'), ...(plan.steps || []).map(step => step.task_id || '')].join(' ').toLowerCase();
    const archived = archives.some(item => item.plan_id === plan.id && item.archived);
    return draftFilter === 'all' && (archiveFilter === 'all' || (archiveFilter === 'archived' ? archived : !archived))
      && (stateFilter === 'all' || (stateFilter === 'attention' ? planNeedsAttention(plan)
        : stateFilter === 'review' ? planLane(plan) === 'ready'
        : stateFilter === 'running' ? planLane(plan) === 'active' && !planNeedsAttention(plan) : planLane(plan) === 'done'))
      && (kindFilter === 'all' || plan.kind === kindFilter) && text.includes(query.trim().toLowerCase());
  }), [plans, drafts, labels, archives, query, kindFilter, archiveFilter, draftFilter, stateFilter, language]);
  const filteredDrafts = drafts.filter(draft => draft.status !== 'STARTED'
    && (stateFilter === 'all' || (stateFilter === 'running' && draft.status === 'QUEUED')
      || (stateFilter === 'done' && draft.status === 'ARCHIVED'))
    && (draftFilter !== 'suggested' || !!draft.suggestion_id)
    && (archiveFilter === 'all' || (archiveFilter === 'archived' ? draft.status === 'ARCHIVED' : draft.status !== 'ARCHIVED'))
    && (kindFilter === 'all' || draft.kind === kindFilter)
    && [draft.id, draft.title, draft.prompt, ui(draft.kind === 'build_site' ? '建站' : '新品上线')]
      .join(' ').toLowerCase().includes(query.trim().toLowerCase()));
  return <section className="commerce-task-board" aria-label={ui("商家任务看板")} data-testid="commerce-task-board">
    <div className="commerce-board-heading"><div><span className="studio-kicker">TASK BOARD</span><h2>{ui("团队任务看板")}</h2>
      <p>{ui("先看进度，再打开任务审查成果。商家发布必须单独确认。")}</p></div>
      <div className="commerce-board-actions"><div className="crew-view-toggle" role="group" aria-label={ui('任务视图')}><button aria-pressed={view==='board'} onClick={()=>changeView('board')}>{ui('看板')}</button><button aria-pressed={view==='list'} onClick={()=>changeView('list')}>{ui('列表')}</button></div><button type="button" onClick={onNewTask}>{ui("新建任务")}</button>
        <button type="button" disabled={refreshing} onClick={onRefresh}>{refreshing ? ui("正在刷新…") : ui("刷新看板")}</button></div></div>
    <div className="commerce-board-filters"><label className="commerce-board-search"><Search size={17}/><span className="sr-only">{ui("搜索商家任务")}</span>
      <input aria-label={ui("搜索商家任务")} value={query} onChange={event => {setQuery(event.target.value); setSelectedDraftIds([]); setSelectedPlanIds([]);}} placeholder={ui("搜索任务编号、建站或新品上线")}/></label>
      <label className="commerce-board-kind">{ui("任务类型")}<select aria-label={ui("筛选商家任务类型")} value={kindFilter} onChange={event => {setKindFilter(event.target.value); setSelectedDraftIds([]); setSelectedPlanIds([]);}}>
        <option value="all">{ui("全部")}</option><option value="build_site">{ui("建站")}</option><option value="launch_products">{ui("新品上线")}</option></select></label>
      <button type="button" className="commerce-filter-toggle" aria-expanded={filtersOpen} aria-controls="board-advanced-filters" onClick={() => setFiltersOpen(value => !value)}>{ui(filtersOpen ? '收起筛选' : '更多筛选')}{(archiveFilter !== 'current' || draftFilter !== 'all' || stateFilter !== 'all') && <span className="commerce-filter-indicator"/>}</button></div>
    <div id="board-advanced-filters" className="commerce-board-advanced" hidden={!filtersOpen} role="group" aria-label={ui('筛选任务')}>
      <label className="commerce-board-kind">{ui("历史")}<select aria-label={ui("筛选归档状态")} value={archiveFilter} onChange={event => {setArchiveFilter(event.target.value); setSelectedPlanIds([]); setSelectedDraftIds([]);}}>
        <option value="current">{ui("未归档")}</option><option value="archived">{ui("已归档")}</option><option value="all">{ui("全部记录")}</option></select></label>
      <label className="commerce-board-kind">{ui("草稿")}<select aria-label={ui("筛选草稿来源")} value={draftFilter} onChange={event => {setDraftFilter(event.target.value); setSelectedDraftIds([]); setSelectedPlanIds([]);}}>
        <option value="all">{ui("全部任务")}</option><option value="drafts">{ui("只看草稿")}</option><option value="suggested">{ui("后续建议")}</option></select></label>
      <label className="commerce-board-kind">{ui("状态")}<select aria-label={ui("筛选任务状态")} value={stateFilter} onChange={event => {setStateFilter(event.target.value); setSelectedDraftIds([]); setSelectedPlanIds([]);}}>
        <option value="all">{ui("全部状态")}</option><option value="attention">{ui("需要处理")}</option><option value="review">{ui("待审查 / 发布")}</option>
        <option value="running">{ui("执行 / 排队")}</option><option value="done">{ui("已结束")}</option></select></label><button type="button" className="commerce-filter-clear" onClick={() => {setQuery(''); setKindFilter('all'); setArchiveFilter('current'); setDraftFilter('all'); setStateFilter('all'); setSelectedDraftIds([]); setSelectedPlanIds([]);}}>{ui('清除筛选')}</button></div>
    {!!activeSelection.length && onBulkArchiveDrafts && <div className="commerce-board-bulk"><span>{ui("已选")}{activeSelection.length}{ui("份草稿")}</span>
      <button type="button" disabled={refreshing} onClick={() => void onBulkStartDrafts?.(activeSelection).then(() => setSelectedDraftIds([]))}>{ui("启动所选草稿")}</button>
      <button type="button" disabled={refreshing} onClick={() => void onBulkArchiveDrafts(activeSelection).then(() => setSelectedDraftIds([]))}>{ui("归档所选草稿")}</button>
      <button type="button" onClick={() => setSelectedDraftIds([])}>{ui("取消选择")}</button></div>}
    {!!selectedPlans.length && <div className="commerce-board-bulk"><span>{ui("已选")}{selectedPlans.length}{ui("项已结束任务")}</span>
      <button type="button" disabled={refreshing || selectedPlans.some(id => archiveIds.has(id))}
        onClick={() => void onArchivePlans(selectedPlans, true).then(() => setSelectedPlanIds([]))}>{ui("归档所选任务")}</button>
      <button type="button" disabled={refreshing || selectedPlans.some(id => !archiveIds.has(id))}
        onClick={() => void onArchivePlans(selectedPlans, false).then(() => setSelectedPlanIds([]))}>{ui("恢复所选任务")}</button>
      <button type="button" onClick={() => setSelectedPlanIds([])}>{ui("取消任务选择")}</button></div>}
    <div className="commerce-board-grid" data-view={view}>{lanes.map(lane => {
      const items = filtered.filter(plan => planLane(plan) === lane.id).reverse();
      const draftItems = filteredDrafts.filter(draft => (draft.status === 'DRAFT' ? 'draft' : draft.status === 'QUEUED' ? 'active' : 'done') === lane.id).reverse();
      return <section key={lane.id} className="commerce-board-lane" data-lane={lane.id} aria-label={ui("{0} {1} 项", [ui(lane.title), items.length + draftItems.length])}>
        <header><div><h3>{ui(lane.title)}</h3><p>{ui(lane.description)}</p></div><span>{items.length + draftItems.length}</span></header>
        {lane.id === 'active' && items.some(planNeedsAttention) && <p className="commerce-board-attention-count">
          <AlertCircle size={13}/>{items.filter(planNeedsAttention).length}{ui("项需要处理")}</p>}
        <div className="commerce-board-cards">{draftItems.map(draft => <div key={draft.id} className="commerce-board-draft">
          {draft.status === 'DRAFT' && onBulkArchiveDrafts && <label className="commerce-board-select"><input type="checkbox"
            aria-label={ui("选择草稿 {0}", [draft.title])} checked={selectedDraftIds.includes(draft.id)}
            onChange={event => setSelectedDraftIds(previous => event.target.checked ? [...previous, draft.id] : previous.filter(id => id !== draft.id))}/></label>}
          <button type="button"
          className="commerce-board-card" data-selected={selectedId === draft.id} aria-pressed={selectedId === draft.id}
          onClick={() => onSelectDraft(draft.id)}>
          <span className="commerce-board-card-top"><strong>{draft.title}</strong><ArrowRight size={16}/></span>
          <span className="commerce-board-card-id">#{draft.id.slice(0, 8)}{ui(" · 版本 ")}{draft.revision} · {draft.status === 'ARCHIVED' ? ui("已归档") : draft.status === 'QUEUED' ? ui("排队中") : ui("草稿")}{draft.suggestion_id ? ui(" · 后续建议") : ''}</span>
          {draft.status === 'QUEUED' && <span>{ui("等待原因：")}{draft.queue_reason === 'capacity' ? ui("执行容量") : draft.queue_reason === 'dependencies' ? ui("前置计划完成") : ui("资料变化或执行条件需处理")}</span>}
          <span className="commerce-board-card-action">{draft.status === 'ARCHIVED' ? ui("可恢复后修改或启动") : ui("查看计划，修改或启动")}</span>
          <span className="commerce-board-card-progress">{draft.proposed_steps?.length || 0}{ui("步预计流程 · 尚未调用模型")}</span>
          </button><details className="commerce-card-menu"><summary aria-label={ui("草稿操作 {0}", [draft.title])}><MoreHorizontal size={17}/></summary>
            <div><button type="button" onClick={() => onSelectDraft(draft.id)}>{draft.status === 'ARCHIVED' ? ui("查看并恢复草稿") : ui("编辑或启动草稿")}</button>
              {draft.status === 'DRAFT' && <button disabled={refreshing} onClick={() => void onBulkStartDrafts?.([draft.id])}>{ui("一次性批准计划并启动")}</button>}
              {draft.status === 'DRAFT' && <button disabled={refreshing} onClick={() => void onBulkStartDrafts?.([draft.id], true)}>{ui("批准并自动应用本地成果")}</button>}
              {draft.status === 'QUEUED' && <button disabled={refreshing} onClick={() => onCancelQueued?.(draft.id)}>{ui("取消排队")}</button>}</div>
          </details></div>)}{items.map(plan => <div key={plan.id} className="commerce-board-draft">
          {planLane(plan) === 'done' && <label className="commerce-board-select"><input type="checkbox"
            aria-label={ui("选择已结束任务 {0}", [labels.find(label => label.plan_id === plan.id)?.title || drafts.find(draft => draft.plan_id === plan.id)?.title || plan.id.slice(0, 8)])}
            checked={selectedPlanIds.includes(plan.id)} onChange={event => setSelectedPlanIds(previous => event.target.checked ? [...previous, plan.id] : previous.filter(id => id !== plan.id))}/></label>}
          <button type="button"
          className="commerce-board-card" data-selected={selectedId === plan.id} aria-pressed={selectedId === plan.id}
          onClick={() => onSelectPlan(plan.id)}>
          <span className="commerce-board-card-top"><strong>{labels.find(label => label.plan_id === plan.id)?.title || drafts.find(draft => draft.plan_id === plan.id)?.title || (plan.kind === 'build_site' ? ui("搭建独立站") : ui("新品上线"))}</strong><ArrowRight size={16}/></span>
          <span className="commerce-board-card-id">#{plan.id.slice(0, 8)}{ui(" · 版本 ")}{plan.revision} · {ui(stateNames[plan.state || ''] || plan.state)}{archiveIds.has(plan.id) ? ui(" · 已归档") : ''}</span>
          {planNeedsAttention(plan) && <span className="commerce-board-attention"><AlertCircle size={13}/>{ui("需处理 ·")}{ui(stateNames[plan.state || ''])}
            {plan.error_code && <small>{plan.error_code}</small>}</span>}
          <span className="commerce-board-card-action">{planNextAction(plan)}</span>
          {dispositions.find(item => item.plan_id === plan.id)?.status === 'APPLIED' && <span>{ui("本地代码已应用 · 商家业务状态另行核验")}</span>}
          {dispositions.find(item => item.plan_id === plan.id)?.status === 'DISMISSED' && <span>{ui("本地代码已放弃 · 原成果保留")}</span>}
          <span className="commerce-board-card-progress">{(plan.steps || []).filter(step => step.status === 'SUCCEEDED').length}/{(plan.steps || []).length}{ui("个角色步骤完成")}</span>
          </button><details className="commerce-card-menu" onClick={event => {if ((event.target as HTMLElement).closest('button')) event.currentTarget.removeAttribute('open');}}>
            <summary aria-label={ui("任务操作 {0}", [plan.id.slice(0, 8)])}><MoreHorizontal size={17}/></summary>
            <div><button type="button" onClick={() => onSelectPlan(plan.id)}>{ui("查看详情与日志")}</button>
              <button type="button" onClick={() => onSelectPlan(plan.id)}>{ui("重命名任务")}</button>
              {plan.code_revision && <button type="button" onClick={() => onSelectPlan(plan.id, 'review')}>{ui("审查代码与整合")}</button>}
              {!['FAILED', 'CANCELLED', 'STALE', 'NEEDS_INPUT', 'PUBLISHING', 'PARTIAL', 'NEEDS_RECONCILIATION'].includes(plan.state || '') &&
                <button disabled={refreshing} onClick={() => onAutoApplyPlan?.(plan.id)}>{ui("一次性自动应用本地代码")}</button>}
              {planLane(plan) === 'done' && <button type="button" disabled={refreshing} onClick={() => void onArchivePlans([plan.id], !archiveIds.has(plan.id))}>
                {archiveIds.has(plan.id) ? ui("恢复任务") : ui("归档任务")}</button>}
              {['PLANNING', 'BUILDING', 'BLOCKED'].includes(plan.state || '') &&
                <button type="button" disabled={refreshing} onClick={() => {onSelectPlan(plan.id); onCancelPlan(plan.id);}}>{ui("取消任务")}</button>}
            </div></details></div>)}
        {!items.length && !draftItems.length && <p className="commerce-board-empty">{query ? ui('没有匹配任务') : ui(lane.id === 'draft' ? '暂无草稿' : lane.id === 'active' ? '还没有正在执行的任务' : lane.id === 'ready' ? '成果就绪后会出现在这里' : '完成的任务会保存在这里')}</p>}</div>
      </section>;
    })}</div>
    <p className="commerce-board-footnote">{ui("“待审查”只包含待审查或已批准待发布的成果。缺资料、受阻和待核对任务留在“进行中”，标明需要处理。“已结束”不代表已发布。")}</p>
  </section>;
}
