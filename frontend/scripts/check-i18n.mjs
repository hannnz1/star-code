import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
const root = path.resolve(import.meta.dirname, '..');
const messages = Object.assign({}, ...['en','extra'].map(name=>JSON.parse(fs.readFileSync(path.join(root,`src/i18n/${name}.json`),'utf8'))));
const placeholders = s => [...s.matchAll(/\{\d+\}/g)].map(m=>m[0]).sort();
for(const [key,value] of Object.entries(messages)) {
 assert.equal(typeof value, 'string', key);
 assert.ok(value.trim(), key);
 assert.ok(!/[\u4e00-\u9fff]/.test(value), `Untranslated English: ${key}`);
 assert.deepEqual(placeholders(key), placeholders(value), `Interpolation mismatch: ${key}`);
}
const files=['main.tsx',...fs.readdirSync(path.join(root,'src/commerce'),{recursive:true}).filter(n=>n.endsWith('.tsx')).map(n=>'commerce/'+n)];
let calls=0;
for(const file of files){
 const ast=ts.createSourceFile(file,fs.readFileSync(path.join(root,'src',file),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 function visit(n){
  if(ts.isCallExpression(n)&&n.expression.getText(ast)==='ui'&&n.arguments[0]&&ts.isStringLiteral(n.arguments[0])){
   const key=n.arguments[0].text;
   if(/[\u4e00-\u9fff]/.test(key))assert.ok(messages[key] || messages[key.trim()],`${file}: missing ${key}`);
   calls++;
  }
  ts.forEachChild(n,visit);
 }
 visit(ast);
}
console.log(`Checked ${Object.keys(messages).length} translations and ${calls} explicit UI calls`);
