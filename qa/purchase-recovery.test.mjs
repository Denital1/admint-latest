import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import ts from 'typescript';
import vm from 'node:vm';
const source = fs.readFileSync(path.join(__dirname,'../app/lib/purchase-recovery.ts'),'utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const api = {};
vm.runInNewContext(compiled,{exports:api,BigInt,Number,JSON,Error});
const valid = {id:1,signature:'1'.repeat(64),mint:'1'.repeat(32)};

test('payment amount is exact down to one lamport',()=>{
  for(const [input,expected] of [['0.000000001',1],['0.1',100000000],['1.234567891',1234567891],['9007199.254740991',Number.MAX_SAFE_INTEGER]]){
    assert.equal(api.purchaseLamports(input),expected);
  }
});
test('invalid or unsafe prices cannot be sent',()=>{
  for(const price of ['0','-1','NaN','Infinity','1e3','0.0000000001','9007199.254740992'])assert.throws(()=>api.purchaseLamports(price));
});
test('valid pending payment survives serialization',()=>{
  assert.equal(JSON.stringify(api.decodePendingPurchase(JSON.stringify(valid))),JSON.stringify(valid));
});
test('corrupt recovery data is ignored safely',()=>{
  for(const input of [null,'{','[]','null','42',JSON.stringify({...valid,id:0}),JSON.stringify({...valid,id:'1'}),JSON.stringify({...valid,signature:'bad'}),JSON.stringify({...valid,mint:'bad'})]){
    assert.equal(api.decodePendingPurchase(input),null);
  }
});
test('recovery data cannot introduce extra properties',()=>{
  const result=api.decodePendingPurchase(JSON.stringify({...valid,cluster:'mainnet',privateKey:'ignored'}));
  assert.equal(Object.keys(result).join(','),'id,signature,mint');
});
