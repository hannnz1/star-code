import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
const root = path.resolve(import.meta.dirname, '..');
const code = ts.transpileModule(fs.readFileSync(path.join(root, 'src/i18n/index.tsx'), 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true}
}).outputText;
function load(saved, blocked = false) {
  const storage = new Map(saved ? [['muse-ui-language', saved]] : []), events = {};
  const exports = {}, document = {documentElement: {lang: ''}};
  vm.runInNewContext(code, {exports, document, window: {addEventListener: (key, callback) => {events[key] = callback;}},
    localStorage: {getItem: key => {if (blocked) throw Error('blocked'); return storage.get(key);},
      setItem: (key, value) => {if (blocked) throw Error('blocked'); storage.set(key, value);}},
    require: name => name.endsWith('.json') ? JSON.parse(fs.readFileSync(path.join(root, 'src/i18n', name), 'utf8'))
      : name === 'react' ? {useSyncExternalStore: (_, snapshot) => snapshot()} : {}});
  return {api: exports, document, storage, events};
}
const {api, document, storage, events} = load();
assert.equal(document.documentElement.lang, 'zh-CN');
api.setUiLanguage('en');
assert.equal(storage.get('muse-ui-language'), 'en');
assert.equal(api.ui('任务看板'), 'Task board');
assert.equal(api.uiFeedback('已保存 3 份建议草稿，可在看板批量启动或取消。'), 'Saved 3 suggestion drafts. Start or cancel them in batches on the board.');
assert.equal(api.uiFeedback('资料已更新，请重新打开项目后提交'), 'Information changed. Reopen the project before submitting');
assert.equal(api.uiFeedback('第 2 行 · 价格: 请检查格式、内容和项目设置'), 'Row 2 · Price: Check format, content and project settings');
assert.equal(api.uiFeedback('商家自定义内容 保持原样'), '商家自定义内容 保持原样');
api.setUiLanguage('zh-CN');
assert.equal(api.uiFeedback('已保存 3 份建议草稿，可在看板批量启动或取消。'), '已保存 3 份建议草稿，可在看板批量启动或取消。');
events.storage({key: 'muse-ui-language', newValue: 'en'});
assert.equal(document.documentElement.lang, 'en');
assert.equal(load('en').document.documentElement.lang, 'en');
const blocked = load(undefined, true);
blocked.api.setUiLanguage('en');
assert.equal(blocked.api.ui('任务看板'), 'Task board');
console.log('Language contracts passed: persistence, live feedback, interpolation, unchanged content and blocked storage');
