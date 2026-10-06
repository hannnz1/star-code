import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, StorePreview, StorePreviewFrame, StorePreviewImage} from '../api.generated';
import type {Api} from './api';

const pages: Record<string, string> = {home: '首页', shop: '商品目录', product: '商品详情', cart: '购物车',
  checkout: '结账', about: '关于我们', contact: '联系我们'};
const checks: Record<string, string> = {pages: '页面访问和标题', layout_desktop: '桌面布局', layout_tablet: '平板布局', layout_mobile: '手机布局', links: '站内链接'};
const reasons: Record<string, string> = {CAPTURE_TIMEOUT: '预览超时', BROWSER_UNAVAILABLE: '预览浏览器不可用',
  CART_PREVIEW_UNAVAILABLE: '购物车预览未就绪', EXTERNAL_RESOURCE_BLOCKED: '已阻止外部资源',
  STOREFRONT_LINK_FAILED: '存在无法核对的链接', PAGE_CAPTURE_FAILED: '页面截图失败', HORIZONTAL_OVERFLOW: '页面横向溢出'};

export function StorePreviewPanel({api, projectId, plan}: {api: Api; projectId: string; plan: CommercePlan}) {
  const [preview, setPreview] = useState<StorePreview | null>(null), [image, setImage] = useState<StorePreviewImage | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true), pending = useRef(false);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  const path = `/commerce/projects/${projectId}/plans/${plan.id}/preview`;
  async function load(frame?: StorePreviewFrame) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try {
      if (frame && preview) {
        const value = await api<StorePreviewImage>(`${path}/${preview.id}/frames/${frame.id}?revision=${plan.revision}`);
        if (alive.current) setImage(value);
      } else {
        const value = await api<StorePreview>(`${path}?revision=${plan.revision}`);
        if (alive.current) {setPreview(value); setImage(null);}
      }
    } catch (e) {
      if (alive.current) {setImage(null); setError('预览尚未生成或资料已更新。' + (e instanceof Error ? e.message : '请刷新团队状态。'));}
    } finally {pending.current = false; if (alive.current) setBusy(false);}
  }
  return <section className="studio-preview-panel">
    <button disabled={busy} onClick={() => void load()}>{ui("查看站点预览")}</button>
    {busy && <p role="status">{ui("正在读取预览…")}</p>}
    {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {preview && <article data-testid="store-preview">
      <h4>{ui("店铺浏览器预览")}</h4>
      <p>{preview.passed ? ui("本次浏览器预览检查通过。") : ui("本次浏览器预览存在待处理问题。")}{ui("尚未通过完整验收，不能据此发布。")}</p>
      <p>{ui("执行隔离、完整购买流程和发布审查仍需验证。")}</p>
      <ul className="studio-preview-checks">{Object.entries(preview.checks).map(([key, passed]) => <li key={key} data-passed={passed}>{ui(checks[key] || key)}：{passed ? ui("通过") : ui("待处理")}</li>)}</ul>
      {!!preview.diagnostics.length && <ul>{preview.diagnostics.map((value, index) => {
        const [reason, kind, width] = value.split(':');
        return <li key={index}>{ui(reasons[reason] || ui("预览检查未完成"))}{kind ? ` · ${ui(pages[kind]) || kind}` : ''}{width ? ` · ${width}px` : ''}</li>;
      })}</ul>}
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 8}}>{preview.frames.map(frame => <button key={frame.id}
        disabled={busy} onClick={() => void load(frame)}>
        {ui(pages[frame.kind])} · {frame.width === 390 ? ui("手机") : frame.width === 768 ? ui("平板") : ui("桌面")} {frame.width}px{frame.sku ? ui(" · {0}", [frame.sku.startsWith('MUSE-PROBE-') ? ui('测试商品（不会发布）') : frame.sku]) : ''}
      </button>)}</div>
      {image && <figure style={{margin: '16px 0', maxWidth: '100%'}}>
        <img alt={ui("{0}预览 · {1}px", [ui(pages[image.frame.kind]), image.frame.width])}
          src={`data:image/png;base64,${image.png_base64}`} style={{maxWidth: '100%', height: 'auto', display: 'block'}}/>
        <figcaption>{image.frame.sku ? ui("{0} · ", [image.frame.sku.startsWith('MUSE-PROBE-') ? ui('测试商品（不会发布）') : 'SKU ' + image.frame.sku]) : ''}{image.frame.width} × {image.frame.height}</figcaption>
      </figure>}
    </article>}
  </section>;
}
