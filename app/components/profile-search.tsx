"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
type Member = {id:number;name:string;avatar:string|null};
export function ProfileSearch(){
  const [query,setQuery]=useState("");
  const [result,setResult]=useState<{query:string;members:Member[];error:boolean}|null>(null);
  const term=query.trim();
  useEffect(()=>{
    if(term.length<2)return;
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      void fetch(`/api/profiles/search/?q=${encodeURIComponent(term)}`,{signal:controller.signal,cache:"no-store"})
        .then(async response=>{if(!response.ok)throw new Error("Search failed");return response.json();})
        .then(data=>setResult({query:term,members:data.results,error:false}))
        .catch(()=>{if(!controller.signal.aborted)setResult({query:term,members:[],error:true});});
    },300);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[term]);
  const current=result?.query===term?result:null;
  return <section className="people-search" aria-label="Find people">
    <label className="market-search"><span aria-hidden="true">⌕</span><input type="search" aria-label="Search profiles" placeholder="Find people by name or wallet…" value={query} onChange={e=>setQuery(e.target.value)}/></label>
    {term.length>0&&term.length<2&&<p role="status">Enter at least 2 characters.</p>}
    {term.length>=2&&<div className="people-results" aria-live="polite" aria-busy={!current}>
      {!current?<p>Searching…</p>:current.error?<p>Could not load profiles. Try again.</p>:current.members.length===0?<p>No profiles found.</p>:current.members.map(member=><Link key={member.id} href={`/profile/${member.id}`} className="people-result">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {member.avatar?<img src={member.avatar} alt=""/>:<span className="people-avatar">{member.name.charAt(0).toUpperCase()}</span>}<span>{member.name}</span><span aria-hidden="true">↗︎</span>
      </Link>)}
    </div>}
  </section>;
}
