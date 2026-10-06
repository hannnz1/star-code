import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, ThemeCodeReview} from '../api.generated';
import type {Api} from './api';
import {MerchantRelease} from './MerchantRelease';
import {CodeIntegration} from './CodeIntegration';

export function ThemeCode({api, projectId, plan, includeRelease = true}: {api: Api; projectId: string; plan: CommercePlan; includeRelease?: boolean}) {
  const [review, setReview] = useState<ThemeCodeReview | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  async function load() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const value = await api<ThemeCodeReview>(`/commerce/projects/${projectId}/plans/${plan.id}/code?revision=${plan.revision}`);
      if (alive.current) setReview(value);
    } catch (e) {if (alive.current) setError(e instanceof Error ? e.message : '代码成果未读取，请刷新团队状态');}
    finally {if (alive.current) setBusy(false);}
  }
  if (!plan.code_revision) return null;
  return <section>
    <button disabled={busy} onClick={() => void load()}>{ui("查看主题代码差异")}</button>
    {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {review && <article data-testid="theme-code-review">
      <h4>{ui("主题代码已封存")}</h4>
      <p>{ui("网站验收和发布尚未完成。这里展示开发角色实际提交的代码，可随项目资料包导出。")}</p>
      <p>{ui("代码版本：")}<code>{review.code_revision}</code></p>
      <p>{ui("代码包摘要：")}<code>{review.package_sha256}</code></p>
      <p>{ui("包含")}{review.files_manifest.length}{ui("个固定主题文件")}</p>
      <pre style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 400, overflow: 'auto'}}>
        {review.diff || ui("保留初始主题，未修改文件内容。")}
      </pre>
    </article>}
    <CodeIntegration api={api} plan={plan}/>
    {includeRelease && <MerchantRelease key={`release:${plan.id}:${plan.revision}`} api={api} projectId={projectId} plan={plan}/>}
  </section>;
}
