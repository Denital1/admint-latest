import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import * as React from "react";
import * as jsx from "react/jsx-runtime";
import {renderToStaticMarkup} from "react-dom/server";
import ts from "typescript";

const code=ts.transpileModule(fs.readFileSync(new URL("../app/orders/[id]/page.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
function render(role,status,extra={}) {
  const order={id:99,listingId:99,title:"Test campaign",price:"0.03",role,status,brief:"Test placement",issue:"",resolution:"",creative:null,proof:null,reviewed:false,messages:[],...extra};
  let hook=0;
  const mocks={
    "react":{...React,useState:initial=>[hook++===0?order:initial,()=>{}],useEffect:()=>{},useCallback:fn=>fn},
    "react/jsx-runtime":jsx,
    "next/link":{default:props=>jsx.jsx("a",props)},
    "next/navigation":{useParams:()=>({id:"99"})},
    "../../lib/auth":{useAuth:()=>({user:{id:1},loading:false})},
    "../../lib/marketplace":{MarketHeader:()=>null,request:()=>{throw new Error("Rendering must not mutate an order");}},
  };
  const exports={};
  vm.runInNewContext(code,{exports,require:name=>{if(!(name in mocks))throw new Error(`Unexpected import ${name}`);return mocks[name];}});
  return renderToStaticMarkup(exports.default());
}
function actions(html){return [...html.matchAll(/name="action"[^>]*value="([^"]+)"/g)].map(match=>match[1]);}

test("buyer and seller receive only the fulfillment action allowed at each stage",()=>{
  const matrix=[
    ["awaiting_creative",["creative"],[]],
    ["creative_submitted",["creative"],["accept"]],
    ["in_progress",[],["deliver"]],
    ["delivered",["complete"],[]],
    ["completed",[],[]],
    ["disputed",[],[]],
    ["refund_requested",[],[]],
  ];
  for(const [status,buyer,seller] of matrix){
    assert.deepEqual(actions(render("buyer",status)),buyer,status+" buyer");
    assert.deepEqual(actions(render("seller",status)),seller,status+" seller");
  }
});
test("delivery requires an image and both participants can view saved evidence",()=>{
  assert.match(render("seller","in_progress"),/<input[^>]*type="file"[^>]*required=""/);
  for(const role of ["buyer","seller"]){
    const html=render(role,"delivered",{creative:"/api/orders/99/file/creative/",proof:"/api/orders/99/file/proof/"});
    assert.match(html,/href="\/api\/orders\/99\/file\/creative\/"/);
    assert.match(html,/src="\/api\/orders\/99\/file\/proof\/"/);
  }
});
test("review is available only to the buyer after completion, once",()=>{
  for(const status of ["awaiting_creative","creative_submitted","in_progress","delivered"]){
    assert.doesNotMatch(render("buyer",status),/name="rating"/);
  }
  assert.match(render("buyer","completed"),/name="rating"/);
  assert.doesNotMatch(render("seller","completed"),/name="rating"/);
  const reviewed=render("buyer","completed",{reviewed:true});
  assert.doesNotMatch(reviewed,/name="rating"/);
  assert.match(reviewed,/Verified review submitted/);
});
