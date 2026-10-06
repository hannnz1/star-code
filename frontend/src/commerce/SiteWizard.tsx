import {ui, uiFeedback} from '../i18n';
import {useSessionDraft} from './useSessionDraft';
import type {SiteBrief, WorkspaceView} from '../api.generated';

export function SiteWizard({workspaces, workspace, busy, onSave}: {
  workspaces: WorkspaceView[]; workspace: string; busy: boolean;
  onSave: (workspaceId: string, brief: SiteBrief) => Promise<void>;
}) {
  const [brand, setBrand] = useSessionDraft('new-store:brand', ''), [language, setLanguage] = useSessionDraft('new-store:language', 'zh-CN');
  const [currency, setCurrency] = useSessionDraft('new-store:currency', 'USD'), [audience, setAudience] = useSessionDraft('new-store:audience', ''), [style, setStyle] = useSessionDraft('new-store:style', '');
  const [chosen, setChosen] = useSessionDraft('new-store:chosen', workspace);
  return <section className="commerce-card"><h2>{ui("建站准备")}</h2><p>{ui("保存品牌、受众和风格，作为后续建站与上新的共同资料。")}</p>
    <form onSubmit={e => {e.preventDefault(); void onSave(chosen || workspace, {brand_name: brand, language, currency, audience, style});}}>
      <div className="commerce-fields">
        <label>{ui("品牌名称")}<input required maxLength={160} value={brand} onChange={e => setBrand(e.target.value)}/></label>
        <label>{ui("工作区")}<select value={chosen || workspace} onChange={e => setChosen(e.target.value)}>{workspaces.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
        <label>{ui("网站语言")}<input required maxLength={24} value={language} onChange={e => setLanguage(e.target.value)}/></label>
        <label>{ui("店铺币种")}<input required maxLength={3} pattern="[A-Z]{3}" value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())}/></label>
      </div>
      <label htmlFor="merchant-audience">{ui("目标受众")}</label><textarea id="merchant-audience" maxLength={4000} value={audience} onChange={e => setAudience(e.target.value)}/>
      <label htmlFor="merchant-style">{ui("风格要求")}</label><textarea id="merchant-style" maxLength={4000} value={style} onChange={e => setStyle(e.target.value)}/>
      <button className="primary" disabled={busy || !brand.trim() || !(chosen || workspace)}>{ui("保存商家项目")}</button>
    </form>
  </section>;
}
