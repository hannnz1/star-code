import {ui} from '../i18n';
import type {CommercePlan,ImportedProducts,StoreProject} from '../api.generated';
export function FlowJourney({kind,project,plans,imports,onTeam,onSettings,onReview}:{
  kind:'build_site'|'launch_products';project:StoreProject;plans:CommercePlan[];imports:ImportedProducts[];
  onTeam:()=>void;onSettings:()=>void;onReview:(plan:CommercePlan)=>void;
}) {
  const relevant=plans.filter(plan=>plan.kind===kind&&!['CANCELLED'].includes(plan.state||''));
  const plan=relevant.filter(p=>p.steps?.length).at(-1);
  const done=!!plan&&plan.state==='SUCCEEDED';
  const stale=plan?.state==='STALE';
  const ready=!!plan&&['REVIEW_REQUIRED','APPROVED','SUCCEEDED'].includes(plan.state||'');
  const stages=kind==='build_site'?[
    {title:'品牌资料',complete:!!project.brief.brand_name},
    {title:'页面结构与风格',complete:relevant.some(p=>!!p.blueprint&&p.state!=='STALE')},
    {title:'团队执行',complete:!stale&&!!plan?.steps?.length&&plan.steps.every(s=>s.status==='SUCCEEDED')},
    {title:'预览与验证',complete:ready},
    {title:'审查发布',complete:done},
  ]:[{title:'商品资料与图片',complete:!!imports.length},{title:'文件校验与内容确认',complete:!!plan&&!!imports.length&&!['NEEDS_INPUT','STALE','FAILED'].includes(plan.state||'')},
    {title:'团队准备',complete:!stale&&!!plan?.steps?.length&&plan.steps.every(s=>s.status==='SUCCEEDED')},
    {title:'变更审查',complete:ready},{title:'发布结果',complete:done}];
  return <section className="crew-flow commerce-card"><h2>{kind==='build_site'?ui('建站流程'):ui('新品上线流程')}</h2>
    <p>{ui('步骤状态来自已保存资料和团队任务；修改资料后需重新验证。')}</p>
    <ol className="crew-stepper">{stages.map((step,index)=><li key={step.title} data-complete={step.complete}><span>{index+1}</span><b>{ui(step.title)}</b><small>{step.complete?ui('已完成'):ui('待完成')}</small></li>)}</ol>
    <div className="crew-flow-actions"><button onClick={onSettings}>{ui('修改品牌与连接资料')}</button><button className="primary" onClick={onTeam}>{ui('准备团队计划')}</button>
      {plan&&<button onClick={()=>onReview(plan)}>{ui('查看成果与发布审查')}</button>}</div>
    {kind==='launch_products'&&!imports.length&&<p role="status">{ui('先校验商品批次；也可保存计划，补齐资料后再启动。')}</p>}
    {plan&&['STALE','NEEDS_INPUT','BLOCKED','PARTIAL','NEEDS_RECONCILIATION','FAILED'].includes(plan.state||'')&&<p role="status">{ui('当前任务需要处理，请到团队任务查看原因。')}</p>}
  </section>;
}
