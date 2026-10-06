import {useSyncExternalStore} from 'react';
import english from './en.json';
import extra from './extra.json';

export type UiLanguage = 'zh-CN' | 'en';
const messages: Record<string, string> = {...english, ...extra};
const listeners = new Set<() => void>();
function initialLanguage(): UiLanguage {
  try {return localStorage.getItem('muse-ui-language') === 'en' ? 'en' : 'zh-CN';}
  catch {return 'zh-CN';}
}
let language = initialLanguage();
function syncDocument() {
  document.documentElement.lang = language;
}
syncDocument();
function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => {listeners.delete(callback);};
}
export function setUiLanguage(value: UiLanguage) {
  if (value !== 'en' && value !== 'zh-CN') return;
  language = value;
  try {localStorage.setItem('muse-ui-language', value);} catch { /* Session switching still works. */ }
  syncDocument();
  for (const callback of listeners) callback();
}
window.addEventListener('storage', event => {
  if (event.key === 'muse-ui-language') {
    language = event.newValue === 'en' ? 'en' : 'zh-CN';
    syncDocument();
    for (const callback of listeners) callback();
  }
});
export function useUiLanguage() {
  return useSyncExternalStore(subscribe, () => language);
}
// Only call with explicit interface messages, never merchant facts or model output.
export function ui(message: string | undefined, values: unknown[] = []): string {
  const source = message ?? '';
  const translated = messages[source] ?? (messages[source.trim()] ? source.replace(source.trim(), messages[source.trim()]) : source);
  const text = language === 'en' ? translated : source;
  return text.replace(/\{(\d+)\}/g, (placeholder, index: string) =>
    Number(index) < values.length ? String(values[Number(index)]) : placeholder);
}
// Feedback is stored in its source language so an already-visible message can switch too.
// Match only catalogued interface templates; arbitrary service output stays unchanged.
export function uiFeedback(message: string): string {
  if (language !== 'en') return message;
  return message.split('\n').map(line => {
    if (messages[line]) return messages[line];
    const fieldError = line.match(/^(?:第 (\d+) 行 · )?([^:]+): (.+)$/);
    if (fieldError && messages[fieldError[3]]) {
      return `${fieldError[1] ? `Row ${fieldError[1]} · ` : ''}${ui(fieldError[2])}: ${ui(fieldError[3])}`;
    }
    for (const [source, target] of Object.entries(messages)) {
      if (!/\{\d+\}/.test(source) || source === target || !/[\u4e00-\u9fff]/.test(source)) continue;
      const indices: string[] = [];
      const pattern = source.split(/(\{\d+\})/).map(part => {
        if (/^\{\d+\}$/.test(part)) {indices.push(part); return '(.*?)';}
        return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      }).join('');
      const match = line.match(new RegExp('^' + pattern + '$'));
      if (match) return target.replace(/\{\d+\}/g, key => match[indices.indexOf(key) + 1]);
    }
    return line;
  }).join('\n');
}
export function LanguageSwitch() {
  const current = useUiLanguage();
  return <div className="language-switch" role="group" aria-label="Language / 界面语言">
    <button type="button" lang="zh-CN" aria-pressed={current === 'zh-CN'} onClick={() => setUiLanguage('zh-CN')}>中文</button>
    <button type="button" lang="en" aria-pressed={current === 'en'} onClick={() => setUiLanguage('en')}>English</button>
  </div>;
}
