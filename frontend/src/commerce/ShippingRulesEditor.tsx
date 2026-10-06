import {useEffect, useRef, useState} from 'react';
import {ui, uiFeedback} from '../i18n';
import type {CommercePlan, ShippingRules, ShippingZone, ShippingDraftQuote, StoreProject} from '../api.generated';
import type {Api} from './api';
import {useSessionDraft} from './useSessionDraft';

function blank(): ShippingZone {
  return {key: 'zone-' + crypto.randomUUID().slice(0, 8), name: '', countries: [], rate: '', free_from: null};
}

export function ShippingRulesEditor({api, project, plan, disabled, onSaved, onBusy}: {
  api: Api; project: StoreProject; plan: CommercePlan; disabled: boolean; onSaved: (plan: CommercePlan) => void; onBusy: (value: boolean) => void;
}) {
  const source = plan.blueprint?.required_settings?.shipping_rules as ShippingRules | undefined;
  const [zones, setZones] = useSessionDraft<ShippingZone[]>(`shipping:${project.id}:${project.revision}:${plan.id}:${JSON.stringify(source || null)}`,source?.zones || [blank()]);
  const [busy, setBusyState] = useState(false), [error, setError] = useState('');
  const [country, setCountry] = useState(''), [subtotal, setSubtotal] = useState(''), [quote, setQuote] = useState<ShippingDraftQuote | null>(null);
  const alive = useRef(true), serial = useRef(0), request = useRef<{body: string; id: string} | null>(null);
  useEffect(() => {alive.current = true; return () => {alive.current = false; serial.current++;};}, []);
  function setBusy(value: boolean) {setBusyState(value); onBusy(value);}
  function change(index: number, update: Partial<ShippingZone>) {
    serial.current++; setQuote(null); setError('');
    setZones(old => old.map((zone, i) => i === index ? {...zone, ...update} : zone));
  }
  async function save() {
    if (busy || disabled) return;
    const frozen = JSON.stringify({expected_revision: project.revision, plan_id: plan.id,
      expected_plan_revision: plan.revision, rules: {currency: project.brief.currency, zones}});
    if (!request.current || request.current.body !== frozen) request.current = {body: frozen, id: crypto.randomUUID()};
    const selected = request.current, started = ++serial.current;
    setBusy(true); setError(''); setQuote(null);
    try {
      const saved = await api<CommercePlan>(`/commerce/projects/${project.id}/shipping-rules`, {method: 'PATCH',
        body: JSON.stringify({...JSON.parse(frozen), client_request_id: selected.id})});
      if (!alive.current || started !== serial.current) return;
      request.current = null; onSaved(saved);
    } catch (e) {if (alive.current && started === serial.current) setError(e instanceof Error ? e.message : 'Error');}
    finally {if (alive.current) setBusy(false);}
  }
  async function calculate() {
    if (busy || disabled || !source) return;
    const started = ++serial.current; setBusy(true); setQuote(null); setError('');
    try {
      const result = await api<ShippingDraftQuote>(`/commerce/projects/${project.id}/shipping-rules/quote`, {method: 'POST',
        body: JSON.stringify({plan_id: plan.id, expected_plan_revision: plan.revision, country: country.trim().toUpperCase(), subtotal})});
      if (alive.current && started === serial.current) setQuote(result);
    } catch (e) {if (alive.current && started === serial.current) setError(e instanceof Error ? e.message : 'Error');}
    finally {if (alive.current) setBusy(false);}
  }
  const dirty = JSON.stringify(zones) !== JSON.stringify(source?.zones || []);
  return <section className="crew-shipping-editor" data-testid="shipping-rules-editor"><h3>{ui('配送规则草稿')}</h3>
    <p>{ui('在 Crew 中填写配送地区、固定运费和免运门槛。保存仅更新建站方案，不会立即修改 WooCommerce；实际生效仍需发布审查和购买验证。')}</p>
    <p>{ui('店铺币种')}：<b>{project.brief.currency}</b></p>
    <form onSubmit={e => {e.preventDefault(); void save();}}><fieldset disabled={busy || disabled}>
      {zones.map((zone, i) => <div className="crew-shipping-zone" key={zone.key}>
        <label>{ui('配送区域名称')}<input aria-label={`${ui('配送区域名称')} ${i+1}`} required maxLength={100} value={zone.name} onChange={e => change(i, {name: e.target.value})}/></label>
        <label>{ui('国家代码')}<input aria-label={`${ui('国家代码')} ${i+1}`} required placeholder="AU, NZ" value={zone.countries.join(', ')} onChange={e => change(i, {countries: e.target.value.toUpperCase().split(',').map(value => value.trim())})}/><small>{ui('填写两位国家代码，以逗号分隔；各区域不能重复国家。')}</small></label>
        <label>{ui('固定运费')}<input aria-label={`${ui('固定运费')} ${i+1}`} type="text" inputMode="decimal" required pattern="[0-9]{1,8}(\.[0-9]{1,2})?" value={zone.rate} onChange={e => change(i, {rate: e.target.value})}/></label>
        <label>{ui('免运门槛')}<input aria-label={`${ui('免运门槛')} ${i+1}`} type="text" inputMode="decimal" pattern="[0-9]{1,8}(\.[0-9]{1,2})?" value={zone.free_from || ''} onChange={e => change(i, {free_from: e.target.value || null})}/><small>{ui('留空表示不提供满额免运。')}</small></label>
        <button type="button" disabled={zones.length === 1} aria-label={`${ui('移除配送区域')} ${i+1}`} onClick={() => {setZones(old => old.filter(item => item.key !== zone.key)); setQuote(null);}}>{ui('移除配送区域')}</button>
      </div>)}
      <div className="commerce-actions"><button type="button" disabled={zones.length >= 10} onClick={() => {setZones(old => [...old, blank()]); setQuote(null);}}>{ui('添加配送区域')}</button><button type="submit" className="primary" disabled={!dirty}>{busy ? ui('正在保存…') : ui('保存配送草稿')}</button><button type="button" disabled={!dirty || !source} onClick={() => {setZones(structuredClone(source!.zones)); setError(''); setQuote(null);}}>{ui('恢复已保存规则')}</button></div>
    </fieldset></form>
    {source && <form onSubmit={e => {e.preventDefault(); void calculate();}}><fieldset disabled={busy || disabled || dirty}><legend>{ui('检验已保存的配送草稿')}</legend><label>{ui('配送国家')}<input required pattern="[A-Za-z]{2}" maxLength={2} value={country} onChange={e => {setCountry(e.target.value); serial.current++; setQuote(null);}}/></label><label>{ui('购物车小计')}<input required inputMode="decimal" pattern="[0-9]{1,8}(\.[0-9]{1,2})?" value={subtotal} onChange={e => {setSubtotal(e.target.value); serial.current++; setQuote(null);}}/></label><button type="submit">{ui('计算草稿运费')}</button></fieldset></form>}
    {quote && <p role="status">{quote.served ? `${quote.amount} ${quote.currency}` : ui('该国家不在配送范围内')}</p>}
    {error && <p role="alert" className="error">{uiFeedback(error)}</p>}
  </section>;
}
