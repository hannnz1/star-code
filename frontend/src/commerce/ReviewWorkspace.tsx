import {useState} from 'react';
import {ui} from '../i18n';
import type {CommercePlan} from '../api.generated';
import type {Api} from './api';
import {ReviewSummary} from './ReviewSummary';
import {VerificationPanel} from './VerificationPanel';
import {StorePreviewPanel} from './StorePreview';
import {ThemeCode} from './ThemeCode';
import {MerchantRelease} from './MerchantRelease';
import {navigateTabs} from './tabs';

const sections = [
  {id: 'overview', title: '审查概览'}, {id: 'code', title: '代码差异与整合'},
  {id: 'preview', title: '页面预览'}, {id: 'verification', title: '验证结果'}, {id: 'publish', title: '发布审查'},
];
export function ReviewWorkspace({api, plan, onPlan, active = true}: {api: Api; plan: CommercePlan; onPlan: (plan: CommercePlan) => void; active?: boolean}) {
  const [section, setSection] = useState('overview');
  return <section className="commerce-review-workspace" data-testid="commerce-review-workspace">
    <div className="commerce-review-nav" role="tablist" aria-label={ui('成果审查内容')} onKeyDown={navigateTabs}>
      {sections.map(item => <button key={item.id} id={`review-tab-${item.id}`} role="tab" tabIndex={section === item.id ? 0 : -1} aria-selected={section === item.id}
        aria-controls={`review-panel-${item.id}`} onClick={() => setSection(item.id)}>{ui(item.title)}</button>)}
    </div>
    <div role="tabpanel" id="review-panel-overview" aria-labelledby="review-tab-overview" hidden={section !== 'overview'}>
      <ReviewSummary api={api} plan={plan}/>
      <div className="commerce-review-shortcuts"><button onClick={() => setSection('code')}>{ui('查看代码并决定整合')}</button>
        <button onClick={() => setSection('preview')}>{ui('检查页面预览')}</button><button onClick={() => setSection('verification')}>{ui('查看验证结果')}</button></div>
    </div>
    <div role="tabpanel" id="review-panel-code" aria-labelledby="review-tab-code" hidden={section !== 'code'}>
      {plan.code_revision ? <ThemeCode api={api} projectId={plan.project_id} plan={plan} includeRelease={false}/>
        : <p className="commerce-panel-empty">{ui('尚未封存代码，团队完成后可在这里审查。')}</p>}
    </div>
    <div role="tabpanel" id="review-panel-preview" aria-labelledby="review-tab-preview" hidden={section !== 'preview'}>
      <StorePreviewPanel api={api} projectId={plan.project_id} plan={plan}/>
    </div>
    <div role="tabpanel" id="review-panel-verification" aria-labelledby="review-tab-verification" hidden={section !== 'verification'}>
      <VerificationPanel api={api} plan={plan} onPlan={onPlan}/>
    </div>
    <div role="tabpanel" id="review-panel-publish" aria-labelledby="review-tab-publish" hidden={section !== 'publish'}>
      {plan.code_revision ? <MerchantRelease api={api} projectId={plan.project_id} plan={plan} active={active && section === 'publish'}/>
        : <p className="commerce-panel-empty">{ui('成果尚未就绪。请先完成团队准备与验证。')}</p>}
    </div>
  </section>;
}
