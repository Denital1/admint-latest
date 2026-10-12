"use client";
import Link from "next/link";
import {AccountButton} from "../components/account-button";
export async function request<T>(path:string,data?:unknown):Promise<T>{
 let csrf="";
 if(data!==undefined){const r=await fetch("/api/auth/session/",{cache:"no-store"});if(!r.ok)throw Error("Could not connect to your account.");csrf=(await r.json()).csrfToken;}
 const form=data instanceof FormData;
 const response=await fetch(`/api/${path}`,{method:data===undefined?"GET":"POST",cache:"no-store",credentials:"include",headers:data===undefined?{}:form?{"X-CSRFToken":csrf}:{"X-CSRFToken":csrf,"Content-Type":"application/json"},body:data===undefined?undefined:form?data:JSON.stringify(data)});
 const result=await response.json().catch(()=>null);if(!response.ok)throw Error(result?.detail||"Unable to complete this request.");return result as T;
}
export function MarketHeader(){return <header className="commerce-header"><Link className="brand" href="/">ad<span>mint</span></Link><nav><Link href="/">Explore</Link><AccountButton/></nav></header>;}
export type Listing={id:number;title:string;tagline:string;price_sol:string;price:string;surfaceType:string;duration:string;status:string;sellerAddress:string;ownerAccountId?:number;txSignature:string;owner:string};
export type Details={description:string;location:string;dimensions:string;audience:string;terms:string;available_from:string;available_until:string;photo:string|null;isOwner:boolean;saved:boolean;reviews:{id:number;name:string;rating:number;text:string}[]};
