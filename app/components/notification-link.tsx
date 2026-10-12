"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {useAuth} from "../lib/auth";
export function NotificationLink(){
 const {user}=useAuth();const [badge,setBadge]=useState<{userId:number;count:number}|null>(null);
 useEffect(()=>{
   if(!user)return;
   let active=true;
   async function refresh(){try{const response=await fetch("/api/profiles/notifications/",{cache:"no-store"});if(response.ok){const data=await response.json();if(active)setBadge({userId:user!.id,count:data.unreadCount});}}catch{}}
   void refresh();const timer=setInterval(()=>{if(document.visibilityState==="visible")void refresh();},30000);
   window.addEventListener("notifications-read",refresh);window.addEventListener("focus",refresh);
   return ()=>{active=false;clearInterval(timer);window.removeEventListener("notifications-read",refresh);window.removeEventListener("focus",refresh);};
 },[user]);
 const count=badge?.userId===user?.id?badge?.count:0;
 return <Link className="notification-link" href="/notifications">Notifications{Boolean(count)&&<span>{count!>99?"99+":count}</span>}</Link>;
}
