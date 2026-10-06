import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, MerchantReleaseReview} from '../api.generated';
import type {Api} from './api';

const operations: Record<string, string> = {create_owned_media: '上传已审查图片', install_theme_package: '安装封存主题',
  create_owned_page: '创建页面草稿', publish_owned_page: '发布页面', set_storefront_options: '设置店铺页面',
  set_owned_navigation: '设置导航', create_product_draft: '创建商品草稿', publish_product: '发布商品'};
const statuses: Record<string, string> = {review: '待审查', approved: '已批准', revoked: '已撤销或过期', consumed: '发布已完成'};

export function MerchantRelease({api, projectId, plan, active = true}: {api: Api; projectId: string; plan: CommercePlan; active?: boolean}) {
  const [review, setReview] = useState<MerchantReleaseReview | null>(null);
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [batchRunning, setBatchRunning] = useState(false), [halted, setHalted] = useState(false), [notice, setNotice] = useState('');
  const stop = useRef(false);
  const alive = useRef(true);
  const visible = useRef(active);
  visible.current = active;
  useEffect(() => {alive.current = true; return () => {alive.current = false; stop.current = true;};}, []);
  useEffect(() => {if (!active) {stop.current = true; setConfirmed(false);}}, [active]);
  const prefix = `/commerce/projects/${projectId}/plans/${plan.id}`;
  async function currentReview() {
    const current = await api<CommercePlan>(prefix);
    return review
      ? await api<MerchantReleaseReview>(`${prefix}/releases/${review.intent_digest}?revision=${current.revision}`)
      : await api<MerchantReleaseReview>(`${prefix}/release-review?revision=${current.revision}`);
  }
  async function load() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const value = await currentReview();
      if (alive.current) {setReview(value); setConfirmed(false); setHalted(false); setNotice('');}
    } catch (e) {if (alive.current) setError(e instanceof Error ? e.message : '发布审查不可用');}
    finally {if (alive.current) setBusy(false);}
  }
  function canPublish(value: MerchantReleaseReview) {
    return value.status === 'approved' && ['APPROVED', 'PUBLISHING'].includes(value.phase)
      && value.completed_steps < value.total_steps
      && (!value.last_attempt ? value.completed_steps === 0
        : value.last_attempt.state === 'SUCCEEDED' && value.last_attempt.effect_verified);
  }
  async function batch() {
    if (!active || busy || halted || !review || !canPublish(review)) return;
    setBusy(true); setBatchRunning(true); setError(''); setNotice(''); stop.current = false;
    let current = review;
    try {
      for (let sent = 0; sent < review.total_steps && alive.current && visible.current && !stop.current && canPublish(current); sent++) {
        const value = await api<MerchantReleaseReview>(`${prefix}/releases/${current.intent_digest}/publish`, {
          method: 'POST', body: JSON.stringify({expected_revision: current.plan_revision})});
        if (value.intent_digest !== current.intent_digest || value.source_digest !== current.source_digest
          || value.code_revision !== current.code_revision || value.project_id !== projectId || value.plan_id !== plan.id
          || JSON.stringify(value.target) !== JSON.stringify(current.target) || value.total_steps !== current.total_steps) {
          throw new Error('发布内容已变化，请重新读取审查。');
        }
        if (alive.current) setReview(value);
        if (value.phase === 'NEEDS_RECONCILIATION' || value.last_attempt?.state === 'NEEDS_RECONCILIATION') {
          if (alive.current) setHalted(true);
          break;
        }
        if (value.completed_steps !== current.completed_steps + 1 || value.plan_revision < current.plan_revision
          || value.last_attempt?.index !== current.completed_steps || value.last_attempt?.state !== 'SUCCEEDED'
          || !value.last_attempt?.effect_verified
          || (value.completed_steps === value.total_steps ? value.status !== 'consumed' || value.phase !== 'SUCCEEDED' : !canPublish(value))) {
          throw new Error('发布进度未得到确认，后续步骤已停止。请只读核对结果。');
        }
        current = value;
      }
      if (alive.current && stop.current) setNotice('已停止后续步骤。已经发送的一步仍按实际回执核对，不会撤销或重发。');
    } catch (e) {
      if (alive.current) {setHalted(true); setError(e instanceof Error ? e.message : '发布未完成，后续步骤已停止。');}
      // No retry, recovery write or automatic restart after a failed batch.
    } finally {
      if (alive.current) {setBusy(false); setBatchRunning(false); setConfirmed(false);}
    }
  }
  async function act(action: 'approve' | 'publish' | 'reconcile') {
    if (!active || busy || !review || (action === 'approve' && (!confirmed || !review.approvable))) return;
    setBusy(true); setError('');
    try {
      const value = await api<MerchantReleaseReview>(`${prefix}/releases/${review.intent_digest}/${action}`, {
        method: 'POST', body: JSON.stringify({expected_revision: review.plan_revision})});
      if (alive.current) {setReview(value); setConfirmed(false);}
    } catch (e) {
      if (alive.current) {setError(e instanceof Error ? e.message : '发布操作未完成，请刷新状态'); setConfirmed(false);}
      // Only refresh local review/accounting state after a failed command.
      // Recovery and another write always require a separate explicit click.
      try {const value = await currentReview(); if (alive.current) setReview(value);} catch (_) {}
    }
    finally {if (alive.current) setBusy(false);}
  }
  if (!plan.code_revision) return null;
  const unknown = review?.last_attempt?.state === 'NEEDS_RECONCILIATION' || review?.phase === 'NEEDS_RECONCILIATION';
  return <section style={{overflowWrap: 'anywhere', minWidth: 0}}>
    <button disabled={busy} onClick={() => void load()}>{ui("查看发布审查")}</button>
    {!review && error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {review && <article data-testid="merchant-release-review">
      <h4>{ui("商家发布审查 · ")}{ui(statuses[review.status] || review.status)}</h4>
      <p>{ui("本次")}{review.workflow === 'build_site' ? ui("建站") : ui("新品上线")}{ui("含 ")}{review.total_steps}{' '}{ui("个固定步骤。批准不会自动发布。")}</p>
      <p>{ui("目标：")}{review.target.environment} · {review.target.public_url}</p>
      <p>{ui("发布内容摘要：")}<code>{review.intent_digest}</code></p>
      <p>{ui("代码版本：")}<code>{review.code_revision}</code></p>
      <p>{ui("主题代码摘要：")}<code>{review.source_digest}</code></p>
      <details><summary>{ui("商品、图片和步骤")}</summary>
        <ul>{review.products.map(product => <li key={product.sku}>{product.sku} · {product.title} · {product.price} {product.currency}{ui(" · 库存 ")}{product.stock}</li>)}</ul>
        <ul>{review.images.map(image => <li key={image.media_ref}>{image.mime_type} · {image.width} × {image.height} · {image.byte_size}{ui("字节")}<code>{image.sha256}</code></li>)}</ul>
        <ol>{review.steps.map(step => <li key={step.key}>{ui(operations[step.kind] || step.kind)} · {step.resource_ref}</li>)}</ol>
      </details>
      <p>{ui("可信验证检查：")}{review.checks.join('、')}</p>
      <label style={{display: 'flex', flexDirection: 'row', alignItems: 'center'}}>
        <input type="checkbox" style={{width: 'auto'}} checked={confirmed} disabled={busy || !review.approvable}
          onChange={e => setConfirmed(e.target.checked)}/>{ui("我已审查目标站点、商品、图片和代码版本")}</label>
      <button disabled={busy || !confirmed || !review.approvable} onClick={() => void act('approve')}>{ui("批准这份发布内容")}</button>
      {review.expires_at && <p>{ui("批准到期时间：")}{new Date(review.expires_at * 1000).toLocaleString()}{ui("。重复点击不延长有效期。")}</p>}
      <p>{ui("执行进度：")}{review.completed_steps} / {review.total_steps}</p>
      {review.last_attempt && <p>{ui("最近一步：")}{review.last_attempt.index + 1} · {review.last_attempt.state} · {review.last_attempt.effect_verified ? ui("效果已核对") : ui("效果尚未核对")}</p>}
      {unknown && <p>{ui("发送结果未知，请只读核对。后续步骤已停止。")}</p>}
      <button disabled={busy || halted || unknown || !canPublish(review)} onClick={() => void act('publish')}>{ui("发布下一步")}</button>
      <button disabled={busy || halted || unknown || !canPublish(review)} onClick={() => void batch()}>{ui("连续发布已批准步骤")}</button>
      {batchRunning && <button onClick={() => {stop.current = true; setNotice('正在停止后续步骤，等待当前一步返回。');}}>{ui("停止后续步骤")}</button>}
      {notice && <p role="status">{uiFeedback(notice)}</p>}
      <button disabled={busy || !review.approved_at} onClick={() => void act('reconcile')}>{ui("只读核对发布结果")}</button>
      {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    </article>}
  </section>;
}
