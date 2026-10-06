import {ui, uiFeedback} from '../i18n';
import {useEffect, useRef, useState} from 'react';
import type {CommercePlan, MerchantReleaseReview, StorePreview, ThemeCodeReview, VerificationStatus} from '../api.generated';
import type {Api} from './api';

type OutputReceipt = {step_id?: string; role?: string; content_hash?: string; payload?: unknown};
const roleNames: Record<string, string> = {store_manager: '店长', site_developer: '网站开发', product_content: '商品内容'};

export function ReviewSummary({api, plan}: {api: Api; plan: CommercePlan}) {
  const [jobs, setJobs] = useState<VerificationStatus[]>([]);
  const [outputs, setOutputs] = useState<OutputReceipt[] | null>(null);
  const [evidence, setEvidence] = useState<{preview: StorePreview | null; review: MerchantReleaseReview | null;
    code: ThemeCodeReview | null; previewError: string; reviewError: string; codeError: string} | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  const path = `/commerce/projects/${plan.project_id}/plans/${plan.id}`;
  useEffect(() => {
    let active = true;
    generation.current++;
    setJobs([]); setOutputs(null); setEvidence(null); setError(''); setBusy(false);
    api<VerificationStatus[]>(path + '/verification-jobs').then(value => {if (active) setJobs(value);})
      .catch(e => {if (active) setError(e instanceof Error ? e.message : '验证状态读取未完成');});
    return () => {active = false; generation.current++;};
  }, [api, path, plan.revision]);
  async function loadOutputs() {
    if (busy) return;
    const version = generation.current;
    setBusy(true); setError('');
    try {const values = await api<OutputReceipt[]>(path + '/outputs'); if (version === generation.current) setOutputs(values);}
    catch (e) {if (version === generation.current) setError(e instanceof Error ? e.message : '团队成果读取未完成');}
    finally {if (version === generation.current) setBusy(false);}
  }
  async function loadEvidence() {
    if (busy || !plan.code_revision) return;
    const version = generation.current;
    setBusy(true); setError('');
    const [preview, review, code] = await Promise.allSettled([
      api<StorePreview>(`${path}/preview?revision=${plan.revision}`),
      api<MerchantReleaseReview>(`${path}/release-review?revision=${plan.revision}`),
      api<ThemeCodeReview>(`${path}/code?revision=${plan.revision}`),
    ]);
    if (version !== generation.current) return;
    setEvidence({
      preview: preview.status === 'fulfilled' ? preview.value : null,
      review: review.status === 'fulfilled' ? review.value : null,
      code: code.status === 'fulfilled' ? code.value : null,
      previewError: preview.status === 'rejected' ? '当前版本尚无可读取的预览证据' : '',
      reviewError: review.status === 'rejected' ? '当前版本尚无可读取的发布审查' : '',
      codeError: code.status === 'rejected' ? '当前版本代码成果不可读取，请刷新并核对' : '',
    });
    setBusy(false);
  }
  const latest = jobs[0];
  const preview = evidence?.preview;
  const review = evidence?.review;
  const code = evidence?.code;
  const codeCurrent = !!code && code.plan_id === plan.id && code.plan_revision === plan.revision && code.code_revision === plan.code_revision;
  const previewCurrent = !!preview && preview.plan_revision === plan.revision
    && preview.project_id === plan.project_id && preview.plan_id === plan.id
    && codeCurrent && preview.source_digest === code?.source_digest;
  const reviewCurrent = !!review && review.plan_revision === plan.revision
    && review.project_id === plan.project_id && review.plan_id === plan.id
    && codeCurrent && review.code_revision === plan.code_revision && review.source_digest === code?.source_digest;
  const changedFiles = code?.diff.split(/(?=^--- before\/)/m).filter(part => part.trim()) || [];
  return <section className="commerce-review-summary" data-testid="commerce-review-summary">
    <div className="commerce-review-heading"><h4>{ui("成果与审查清单")}</h4><p>{ui("审查实际成果、测试和预览，再决定是否批准发布。")}</p></div>
    <ul className="commerce-review-checks">
      <li><b>{ui("角色成果")}</b><span>{(plan.steps || []).filter(step => !!step.output_hash).length}/{(plan.steps || []).length}{' '}{ui("已封存")}</span></li>
      <li><b>{ui("主题代码")}</b><span>{plan.code_revision ? ui("版本 {0}，可查看差异", [plan.code_revision.slice(0, 8)]) : ui("尚未封存")}</span></li>
      <li><b>{ui("后台验证")}</b><span>{latest ? ui("{0}{1}{2}", [latest.state, latest.plan_revision === plan.revision ? '' : ui(' · 版本已变化'), latest.error_code ? ` · ${latest.error_code}` : '']) : ui("尚未运行")}</span></li>
      <li><b>{ui("页面预览")}</b><span>{preview ? ui("{0} 张截图 · {1}{2}", [preview.frames.length, ui(preview.passed ? '检查通过' : '检查未通过'), previewCurrent ? '' : ui(' · 版本未绑定')]) : evidence?.previewError ? uiFeedback(evidence.previewError) : ui("尚未读取")}</span></li>
      <li><b>{ui("目标环境")}</b><span>{review ? ui("{0} · {1}{2}", [review.target.environment, review.target.public_url, reviewCurrent ? '' : ui(' · 版本已变化')]) : evidence?.reviewError ? uiFeedback(evidence.reviewError) : ui("尚未读取")}</span></li>
      <li><b>{ui("发布审查")}</b><span>{plan.state === 'REVIEW_REQUIRED' ? ui("待商家审查") : plan.state === 'APPROVED' ? ui("已批准，尚未自动发布") : plan.state === 'SUCCEEDED' ? ui("已完成") : ui("尚未就绪")}</span></li>
    </ul>
    <button type="button" disabled={busy} onClick={() => void loadOutputs()}>{busy ? ui("正在读取…") : ui("查看角色提交的成果")}</button>
    <button type="button" disabled={busy || !plan.code_revision} onClick={() => void loadEvidence()}>{ui("读取代码、预览与发布目标")}</button>
    {evidence?.codeError && <p role="alert" className="error commerce-error">{uiFeedback(evidence.codeError)}</p>}
    {code && <div className="commerce-output-list"><h4>{ui("逐文件代码审查")}</h4>
      <p>{code.files_manifest.length}{ui("个封存文件 ·")}{changedFiles.length}{ui("个文件有差异 ·")}{codeCurrent ? ui("对应当前计划版本") : ui("版本已变化，请重新读取")}</p>
      {changedFiles.map((part, index) => <details key={index}><summary>{part.split('\n')[0].replace('--- before/', '')}</summary><pre>{part}</pre></details>)}
      {!changedFiles.length && <p>{ui("代码内容与本计划起点一致。")}</p>}
      <details><summary>{ui("封存文件清单与摘要")}</summary><pre>{JSON.stringify(code.files_manifest, null, 2)}</pre></details>
    </div>}
    {latest?.error_code && <p role="status">{ui("验证问题：")}{latest.error_code}{ui("。在下方「店铺验证」查看失败阶段并只读核对结果。")}</p>}
    {evidence && <p>{ui("预览是生成截图，站点验证须以后台验证结果为准。缺少证据或版本不一致时，请刷新团队状态后重新审查。")}</p>}
    {error && <p role="alert" className="error commerce-error">{uiFeedback(error)}</p>}
    {outputs && (outputs.length ? <div className="commerce-output-list">{outputs.map((output, index) => <details key={`${output.step_id}-${index}`}>
      <summary>{ui(roleNames[output.role || ''] || output.role || ui("角色成果"))} · {output.content_hash?.slice(0, 10) || ui("未提供摘要")}</summary>
      <pre>{JSON.stringify(output.payload, null, 2)}</pre>
    </details>)}</div> : <p>{ui("当前计划尚无已提交的角色成果。")}</p>)}
  </section>;
}
