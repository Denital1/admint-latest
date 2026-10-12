"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {useAuth} from "../lib/auth";
type Item={id:number;listingId:number;title:string;price:string;status:string;ownerId:number|null;ownerName:string;createdAt:string;read:boolean};
export default function Notifications(){
 const {user,loading}=useAuth();const [items,setItems]=useState<Item[]>([]);const [cursor,setCursor]=useState<number|null>(null);const [busy,setBusy]=useState(true);const [error,setError]=useState("");
 useEffect(()=>{
   if(!user)return;
   const controller=new AbortController();
   void fetch("/api/profiles/notifications/",{cache:"no-store",signal:controller.signal}).then(async r=>{if(!r.ok)throw Error("Could not load notifications.");return r.json();}).then(data=>{setItems(data.results);setCursor(data.nextCursor);setBusy(false);}).catch(e=>{if(!controller.signal.aborted){setError(e.message);setBusy(false);}});
   return ()=>controller.abort();
 },[user]);
 async function more(){setBusy(true);setError("");try{const response=await fetch(`/api/profiles/notifications/?before=${cursor}`,{cache:"no-store"});if(!response.ok)throw Error("Could not load notifications.");const data=await response.json();setItems(current=>[...current,...data.results]);setCursor(data.nextCursor);}catch(e){setError(e instanceof Error?e.message:"Please try again.");}finally{setBusy(false);}}
 async function markRead(){setError("");try{const session=await fetch("/api/auth/session/",{cache:"no-store"});if(!session.ok)throw Error("Could not update notifications.");const {csrfToken}=await session.json();const ids=items.filter(i=>!i.read).map(i=>i.id).slice(0,100);const response=await fetch("/api/profiles/notifications/read/",{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrfToken},body:JSON.stringify({ids})});if(!response.ok)throw Error("Could not update notifications.");setItems(current=>current.map(i=>ids.includes(i.id)?{...i,read:true}:i));window.dispatchEvent(new Event("notifications-read"));}catch(e){setError(e instanceof Error?e.message:"Please try again.");}}
 return <main className="notification-page"><header><Link className="brand" href="/">ad<span>mint</span></Link><Link href="/">Marketplace ↗︎</Link></header><div className="notification-heading"><div><h1>Notifications</h1><p>New surfaces from people you follow.</p></div>{user&&items.some(i=>!i.read)&&<button className="button-text" onClick={()=>void markRead()}>Mark as read ✓</button>}</div>
 {loading?<p>Loading…</p>:!user?<p><Link href="/login">Log in</Link> to see your notifications.</p>:<>{error&&<p role="alert">{error}</p>}{busy&&items.length===0?<p>Loading…</p>:items.length===0&&!error?<div className="collection-empty"><h3>You’re all caught up</h3><p>Follow people to hear about their next listing.</p><Link href="/">Find people ↗︎</Link></div>:<div className="notification-list">{items.map(item=><article key={item.id} className={`notification-item ${item.read?"":"unread"}`}><div><span className="notification-dot"/>{item.ownerId?<Link href={`/profile/${item.ownerId}`}>{item.ownerName}</Link>:<span>{item.ownerName}</span>}<span>listed a new surface</span></div><Link className="notification-title" href={`/listing/${item.listingId}`}>{item.title} ↗︎</Link><footer><span>{item.price} SOL · {item.status}</span><time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleDateString()}</time></footer></article>)}</div>}{cursor&&<button className="button-solid" disabled={busy} onClick={()=>void more()}>{busy?"Loading…":"Show more"}</button>}</>}
 </main>;
}
