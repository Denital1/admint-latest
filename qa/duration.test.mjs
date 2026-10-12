import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import ts from 'typescript';
import vm from 'node:vm';
const source = fs.readFileSync(path.join(__dirname,'../app/lib/duration.ts'),'utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const api = {};
vm.runInNewContext(compiled,{exports:api,BigInt,Number,JSON,Error});

test('fractional durations normalize to whole days, hours and minutes',()=>{
  for(const [value,unit,expected] of [['5.5','days','5 days and 12 hours'],['1.25','hours','1 hour and 15 minutes'],['1.5','weeks','1 week, 3 days and 12 hours'],['1.5','months','1 month and 15 days'],['1.5','years','1 year, 182 days and 12 hours'],['90','minutes','90 minutes']]){
    assert.equal(api.formatDuration(value,unit),expected);
  }
});
test('all units convert to exact minute totals',()=>{
  for(const [unit,minutes] of [['minutes',1],['hours',60],['days',1440],['weeks',10080],['months',43200],['years',525600]])assert.equal(api.durationMinutes('1',unit),minutes);
  assert.equal(api.durationMinutes('5.5','days'),7920);
});
test('minute rounding and singular units are predictable',()=>{
  assert.equal(api.formatDuration('0.5','minutes'),'1 minute');
  assert.equal(api.formatDuration('1.01','hours'),'1 hour and 1 minute');
  assert.equal(api.formatDuration('1.','days'),'1 day');
});
test('invalid, zero, too small and unsafe durations are rejected',()=>{
  for(const value of ['', '.', '0','0.49','-1','1e3','5 days','5,5','NaN','Infinity','99999999999999999'])assert.equal(api.formatDuration(value,'minutes'),null);
  assert.equal(api.formatDuration('9999999999999999','years'),null);
  assert.equal(api.durationMinutes('1','bad-unit'),null);
});
