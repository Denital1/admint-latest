"use client";
import {createContext,useContext,useRef,useState,type PropsWithChildren} from "react";
type Stage="prepare"|"wallet"|"send"|"confirm"|"save"|"success"|"error";
type Progress={stage:Stage;price:string;signature?:string;explorer?:string;error?:string};
type Context={active:boolean;start:(price:string)=>boolean;advance:(stage:Stage,details?:Partial<Progress>)=>void};
const Context=createContext<Context|null>(null);
const steps=[{id:"prepare",label:"Preparing purchase",description:"Checking your balance and reserving the surface."},{id:"wallet",label:"Confirm in Phantom",description:"Approve the transaction in your wallet."},{id:"send",label:"Sending transaction",description:"Submitting your signed transaction."},{id:"confirm",label:"Waiting for confirmation",description:"Solana is confirming your transaction."},{id:"save",label:"Updating your purchase",description:"Verifying the payment and saving your ad right."}];
export function TransactionProvider({children}:PropsWithChildren){
  const [progress,setProgress]=useState<Progress|null>(null);
  const locked=useRef(false);
  function start(price:string){if(locked.current)return false;locked.current=true;setProgress({stage:"prepare",price});return true;}
  function advance(stage:Stage,details?:Partial<Progress>){if(stage==="success"||stage==="error")locked.current=false;setProgress(current=>current?{...current,...details,stage}:null);}
  const active=!!progress&&!['success','error'].includes(progress.stage);
  return <Context.Provider value={{active,start,advance}}>{children}{progress&&<TransactionProgress progress={progress} onClose={()=>setProgress(null)}/>}</Context.Provider>;
}
export function useTransaction(){const value=useContext(Context);if(!value)throw new Error("TransactionProvider missing");return value;}
export function TransactionProgress({progress,onClose}:{progress:Progress;onClose:()=>void}){
  const {stage}=progress;const current=steps.findIndex(step=>step.id===stage);const done=stage==="success";const failed=stage==="error";
  const label=done?"Purchase complete":failed?(progress.signature?"Confirmation needs attention":"Purchase not completed"):steps[current].label;
  return <section className={`transaction-progress ${done?'tx-done':''} ${failed?'tx-error':''}`} aria-label="Purchase progress">
    <header><span className="tx-eyebrow">YOUR PURCHASE</span>{(done||failed)&&<button onClick={onClose} aria-label="Dismiss purchase status">×</button>}<span className="tx-price">{progress.price}</span></header>
    <div className="tx-visual" aria-hidden="true"><div className="tx-orbit"/><div className="tx-orbit tx-orbit-second"/><div className="tx-token">{done?<svg viewBox="0 0 48 48"><path d="M12 25L21 34L37 15"/></svg>:failed?<span>!</span>:<span>ad.</span>}</div>{!done&&!failed&&<span className="tx-satellite"/>}</div>
    <div className="tx-status" role="status" aria-live="polite" aria-atomic="true"><h2>{label}</h2><p>{done?"Your ad right is saved to your account.":failed?(progress.error||"Please check your transaction before trying again."):steps[current].description}</p></div>
    {!done&&!failed&&<ol className="tx-steps" aria-label="Transaction stages">{steps.map((step,index)=><li key={step.id} className={index<current?'complete':index===current?'current':''} aria-current={index===current?'step':undefined}><span>{index<current?'✓':String(index+1).padStart(2,'0')}</span><b>{step.label}</b>{index===current&&<i className="tx-inline-spinner" aria-hidden="true"/>}</li>)}</ol>}
    {progress.signature&&<a className="tx-explorer" href={progress.explorer} target="_blank" rel="noopener noreferrer">View transaction ↗︎</a>}
    {failed&&progress.signature&&<p className="tx-caution">A transaction was sent. Check its status before buying again.</p>}
    {done&&<button className="button-solid tx-close" onClick={onClose}>Done <span>✓</span></button>}
  </section>;
}
