"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {request,MarketHeader} from "../lib/marketplace";
import {getListings,type Surface} from "../lib/api";
import {useAuth} from "../lib/auth";
export default function Saved(){const {user,loading}=useAuth();const [items,setItems]=useState<Surface[]|null>(null);const [error,setError]=useState("");useEffect(()=>{if(!user)return;let active=true;Promise.all([request<{ids:number[]}>("saved/"),getListings()]).then(([d,l])=>{if(active)setItems(l.filter(i=>d.ids.includes(i.id)));}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[user]);return <main className="commerce-page"><MarketHeader/><div className="commerce-title"><h1>Saved <em>spaces.</em></h1></div>{error&&<p role="alert">{error}</p>}{loading?<p>Loading…</p>:!user?<Link href="/login">Log in to see saved surfaces</Link>:!items?<p>Loading…</p>:items.length===0?<p>No saved surfaces yet. Open a listing and tap Save.</p>:<div className="order-grid">{items.map(i=><Link className="commerce-panel order-card" key={i.id} href={`/listing/${i.id}`}><span>{i.type} · {i.status}</span><h2>{i.title}</h2><p>{i.price}</p></Link>)}</div>}</main>;}
