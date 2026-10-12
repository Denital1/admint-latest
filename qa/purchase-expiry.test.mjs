import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import * as web3 from "@solana/web3.js";
import * as token from "@solana/spl-token";
import ts from "typescript";

function compile(path) {
  return ts.transpileModule(fs.readFileSync(new URL(path, import.meta.url), "utf8"), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
}
const componentCode=compile("../app/components/buy-rights-button.tsx");
const recoveryApi={};
vm.runInNewContext(compile("../app/lib/purchase-recovery.ts"),{exports:recoveryApi,BigInt,Number,JSON,Error});

function fixture({expired=false,changed=false,heightUnavailable=false,resume=false,purchaseStatus="pending",confirmationError=false,readUnavailable=false}={}) {
  const buyer=web3.Keypair.generate(),seller=web3.Keypair.generate();
  const blockhash=web3.Keypair.generate().publicKey.toBase58();
  const signature="1".repeat(64);
  const calls={sent:0,cancelled:0,confirmed:0,purchased:0,refreshed:0,options:null,states:[]};
  const storage=new Map();
  if(resume)storage.set(`admint:purchase:devnet:${buyer.publicKey.toBase58()}:1`,JSON.stringify({id:1,signature,mint:seller.publicKey.toBase58()}));
  class Connection {
    async getMinimumBalanceForRentExemption(){return 1000000;}
    async getBalance(){return 1000000000;}
    async getLatestBlockhash(){return {blockhash,lastValidBlockHeight:100};}
    async getFeeForMessage(){return {value:5000};}
    async simulateTransaction(){return {value:{err:null}};}
    async getBlockHeight(){if(heightUnavailable)throw new Error("RPC unavailable");return expired?101:100;}
    async sendRawTransaction(bytes,options){
      assert.equal(storage.size,1,"recovery must be saved before broadcasting");
      assert.ok(web3.Transaction.from(bytes).verifySignatures());
      calls.sent++;calls.options=options;return signature;
    }
    async getSignatureStatus(){return {value:{confirmationStatus:"confirmed"}};}
  }
  const wallet={account:{address:buyer.publicKey.toBase58()},async signTransaction(bytes){
    const transaction=web3.Transaction.from(bytes);
    if(changed)transaction.recentBlockhash=web3.Keypair.generate().publicKey.toBase58();
    transaction.sign(buyer);return transaction.serialize();
  }};
  const transaction={active:false,start:()=>true,advance:(state,data)=>calls.states.push({state,...data})};
  const mocks={
    "react/jsx-runtime":{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})},
    "@solana/web3.js":{...web3,Connection},"@solana/spl-token":token,
    "@solana/kit":{getBase58Decoder:()=>({decode:()=>signature})},
    "sonner":{toast:{error:()=>{},info:()=>{}}},
    "../lib/purchase-recovery":recoveryApi,
    "./transaction-progress":{useTransaction:()=>transaction},
    "../lib/auth":{useAuth:()=>({user:{id:1,wallets:[wallet.account.address]}})},
    "../lib/wallet/context":{useWallet:()=>({wallet,status:"connected"})},
    "./cluster-context":{useCluster:()=>({cluster:"devnet",getExplorerUrl:path=>path})},
    "../lib/solana-client":{getClusterUrl:()=>"mock://no-network"},
    "../lib/api":{preparePurchase:async()=>({id:1,price_sol:"0.03"}),cancelPurchase:async()=>{calls.cancelled++;},confirmPurchase:async()=>{calls.confirmed++;if(confirmationError)throw new Error("RPC still checking this transaction; retry later.");},getMyPurchases:async()=>{if(readUnavailable)throw new Error("Session unavailable");return [{id:1,status:purchaseStatus,tx_signature:signature,verification_message:"The expired attempt was not completed. You can try again."}];}},
  };
  const exports={};
  vm.runInNewContext(componentCode,{exports,require:name=>{if(!(name in mocks))throw new Error(`Unmocked dependency: ${name}`);return mocks[name];},Buffer,Event,Error,crypto:webcrypto,console:{error:()=>{}},localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},window:{dispatchEvent:()=>{calls.refreshed++;}},setTimeout});
  const button=exports.BuyRightsButton({listingId:1,sellerAddress:seller.publicKey.toBase58(),price:"0.03 SOL",onPurchased:()=>{calls.purchased++;},onReconciled:async()=>{calls.refreshed++;}});
  return {calls,storage,run:()=>button.props.onClick()};
}

test("expired wallet approval never broadcasts or creates recovery debt",async()=>{
  const f=fixture({expired:true});await f.run();assert.equal(f.calls.sent,0);assert.equal(f.calls.cancelled,1);assert.equal(f.calls.confirmed,0);assert.equal(f.storage.size,0);assert.match(f.calls.states.at(-1).error,/expired/);
});
test("wallet-modified blockhash is rejected before broadcast",async()=>{
  const f=fixture({changed:true});await f.run();assert.equal(f.calls.sent,0);assert.equal(f.calls.cancelled,1);assert.match(f.calls.states.at(-1).error,/changed/);
});
test("unavailable expiry check cannot accidentally send payment",async()=>{
  const f=fixture({heightUnavailable:true});await f.run();assert.equal(f.calls.sent,0);assert.equal(f.calls.cancelled,1);assert.equal(f.storage.size,0);
});
test("last valid block height can pay once with RPC preflight and persist",async()=>{
  const f=fixture();await f.run();assert.equal(f.calls.sent,1);assert.equal(f.calls.cancelled,0);assert.equal(f.calls.confirmed,1);assert.equal(f.calls.options.skipPreflight,false);assert.equal(f.storage.size,0);assert.equal(f.calls.states.at(-1).state,"success");
});

test("resume reaches server verification directly without sending another payment",async()=>{
  const f=fixture({resume:true});await f.run();assert.equal(f.calls.confirmed,1);assert.equal(f.calls.sent,0);assert.equal(f.calls.purchased,1);assert.equal(f.storage.size,0);
});
test("settled failed purchase removes stale recovery and refreshes availability",async()=>{
  const f=fixture({resume:true,purchaseStatus:"failed"});await f.run();assert.equal(f.calls.confirmed,0);assert.equal(f.calls.sent,0);assert.equal(f.calls.purchased,0);assert.equal(f.storage.size,0);assert.equal(f.calls.refreshed,1);assert.equal(f.calls.states.at(-1).signature,undefined);assert.match(f.calls.states.at(-1).error,/expired/);
});
test("already confirmed purchase recovers idempotently",async()=>{
  const f=fixture({resume:true,purchaseStatus:"confirmed"});await f.run();assert.equal(f.calls.confirmed,0);assert.equal(f.calls.purchased,1);assert.equal(f.calls.sent,0);assert.equal(f.storage.size,0);
});
test("uncertain chain confirmation preserves recovery without resubmitting funds",async()=>{
  const f=fixture({resume:true,confirmationError:true});await f.run();assert.equal(f.calls.confirmed,1);assert.equal(f.calls.sent,0);assert.equal(f.storage.size,1);assert.equal(f.calls.refreshed,0);assert.match(f.calls.states.at(-1).error,/RPC still checking/);
});
test("unavailable server preserves the original recovery",async()=>{
  const f=fixture({resume:true,readUnavailable:true});await f.run();assert.equal(f.calls.sent,0);assert.equal(f.calls.confirmed,0);assert.equal(f.storage.size,1);
});
