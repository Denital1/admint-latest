"use client";
/* eslint-disable @next/next/no-img-element -- Local database avatar endpoint; images are normalized on upload. */
import Link from "next/link";
import {useState, useEffect, useCallback, type FormEvent} from "react";
import {useAuth, authRequest} from "../lib/auth";

type Member = {id:number; name:string; avatar:string|null};
type Item = {id:number; title:string; emoji:string; type:string; price:string; status:string; duration:string; purchaseId?:number; date?:string};
type Profile = Member & {bio:string; joined:string; wallets:string[]; isOwner:boolean; isFollowing:boolean;
  counts:{sold:number; bought:number; listings:number; followers:number; following:number};
  sold:Item[]; bought:Item[]; listings:Item[]; followers:Member[]; following:Member[]};
type Tab = "listings"|"sold"|"bought"|"followers"|"following";
export function ProfileView({profileId}:{profileId?:string}) {
  const {user, loading:authLoading, refresh} = useAuth();
  const id = profileId || (user ? String(user.id) : "");
  const [profile,setProfile] = useState<Profile|null>(null);
  const [loadedId,setLoadedId] = useState("");
  const [error,setError] = useState("");
  const [tab,setTab] = useState<Tab>("listings");
  const [editing,setEditing] = useState(false);
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState("");
  const load = useCallback(async () => {
    const response = await fetch(`/api/profiles/${encodeURIComponent(id)}/`, {credentials:"include",cache:"no-store"});
    if (!response.ok) throw new Error(response.status === 404 ? "Profile not found." : "Unable to load profile. Please try again.");
    return await response.json() as Profile;
  }, [id]);
  useEffect(() => { if (!id) return; let active=true; load().then((p) => {if(active){setProfile(p);setLoadedId(id);setError("");}}).catch((e) => {if(active){setError(e.message);setLoadedId(id);}}); return () => {active=false;}; }, [id,load,user?.id]);
  async function toggleFollow() {
    if (!user) { window.location.assign("/login"); return; }
    if (!profile) return;
    setBusy(true);setError("");
    try {
      const session=await authRequest("session");
      const response=await fetch(`/api/profiles/${profile.id}/follow/`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json","X-CSRFToken":session.csrfToken},body:JSON.stringify({following:!profile.isFollowing})});
      if(!response.ok) {const data=await response.json(); throw new Error(data.detail || "Unable to update follow.");}
      setProfile(await load());
    }catch(e){setError(e instanceof Error ? e.message : "Unable to update follow.");}finally{setBusy(false);}
  }
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form=new FormData(event.currentTarget);setBusy(true);setError("");setNotice("");
    try{
      const file=form.get("avatar"); if(file instanceof File && file.size>5*1024*1024) throw new Error("Choose an image smaller than 5 MB.");
      const session=await authRequest("session");
      const response=await fetch("/api/profiles/update/",{method:"POST",credentials:"include",headers:{"X-CSRFToken":session.csrfToken},body:form});
      if(!response.ok){const data=await response.json();throw new Error(data.detail || "Unable to save profile.");}
      setProfile(await load());await refresh();setEditing(false);setNotice("Your profile has been saved.");
    }catch(e){setError(e instanceof Error ? e.message : "Unable to save profile.");}finally{setBusy(false);}
  }
  const control="rounded-xl border border-foreground/15 px-5 py-2.5 text-sm font-medium transition hover:bg-foreground/10 disabled:opacity-50";
  const tabs: {key:Tab;label:string}[]=[{key:"listings",label:"Surfaces"},{key:"sold",label:"Sold"},{key:"bought",label:"Purchased"},{key:"followers",label:"Followers"},{key:"following",label:"Following"}];
  const ready=profile && loadedId===id;
  return <main className="min-h-screen bg-background px-5 py-8 text-foreground sm:px-10">
    <div className="mx-auto max-w-5xl">
      <nav className="mb-8 flex items-center justify-between"><Link href="/" className="text-xl font-bold">AdMint<span className="text-primary">.</span></Link><div className="flex gap-5 text-sm text-foreground/60"><Link href="/">Marketplace</Link><Link href={user ? "/profile" : "/login"}>{user ? "My profile" : "Log in"}</Link></div></nav>
      {error && <div role="alert" className="mb-5 rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-200">{error}</div>}
      {notice && <p role="status" className="mb-5 text-sm text-emerald-300">{notice}</p>}
      {!id && !authLoading ? <section className="rounded-3xl border border-foreground/10 p-10"><h1 className="text-3xl font-semibold">Your AdMint profile</h1><p className="my-5 text-foreground/50">Log in to build your profile and follow other members.</p><Link href="/login" className={control}>Log in / Sign up →</Link></section> : !ready ? <p role="status">{error ? "" : "Loading profile…"}</p> : <>
        <section className="overflow-hidden rounded-3xl border border-foreground/10 bg-card">
          <div className="h-36 bg-gradient-to-r from-primary/35 via-primary/10 to-secondary sm:h-44"><div className="h-full bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.15),transparent)]"/></div>
          <div className="px-6 pb-7 sm:px-9">
            <div className="flex flex-wrap items-end justify-between gap-5"><div className="-mt-12 flex h-24 w-24 items-center justify-center overflow-hidden rounded-3xl border-4 border-card bg-secondary text-4xl font-bold shadow-xl">{profile.avatar ? <img src={profile.avatar} alt={`${profile.name}'s profile`} className="h-full w-full object-cover"/> : profile.name.slice(0,1).toUpperCase()}</div>
              <div className="flex gap-3 pt-4">{profile.isOwner ? <><Link href="/login" className={control}>Account settings</Link><button onClick={()=>setEditing(!editing)} className={control}>{editing ? "Cancel" : "Edit profile"}</button></> : <button disabled={busy} onClick={toggleFollow} className={control+" bg-primary/25 text-primary"}>{busy ? "Updating…" : profile.isFollowing ? "Following ✓ · Unfollow" : "Follow +"}</button>}</div>
            </div>
            <h1 className="mt-5 text-3xl font-semibold tracking-tight">{profile.name}</h1>
            <p className="mt-2 text-sm text-foreground/35">Member #{profile.id} · Joined {new Date(profile.joined).toLocaleDateString("en-US",{month:"long",year:"numeric"})}</p>
            <p className="mt-4 max-w-2xl whitespace-pre-wrap text-sm leading-6 text-foreground/65">{profile.bio}</p>
            <div className="mt-6 flex flex-wrap gap-x-7 gap-y-4">{tabs.filter(t=>t.key!=="listings").map(t=><button key={t.key} onClick={()=>setTab(t.key)} className="text-left"><span className="text-xl font-semibold">{profile.counts[t.key]}</span><span className="ml-2 text-sm text-foreground/45">{t.label}</span></button>)}</div>
            {profile.wallets.length>0 && <details className="mt-5 text-xs text-foreground/40"><summary className="cursor-pointer">Verified wallets ({profile.wallets.length})</summary>{profile.wallets.map(wallet=><p key={wallet} className="mt-2 break-all font-mono">{wallet}</p>)}</details>}
          </div>
        </section>
        {editing && profile.isOwner && <form onSubmit={save} className="mt-5 space-y-5 rounded-2xl border border-foreground/10 bg-card p-6">
          <h2 className="text-lg font-semibold">Edit your profile</h2>
          <label className="block text-sm">Display name<input name="name" defaultValue={profile.name} required maxLength={80} className="mt-2 block w-full rounded-xl border border-foreground/15 bg-foreground/5 p-3"/></label>
          <label className="block text-sm">Bio<textarea name="bio" defaultValue={profile.bio} maxLength={300} rows={3} className="mt-2 block w-full rounded-xl border border-foreground/15 bg-foreground/5 p-3"/></label>
          <label className="block text-sm">Profile photo<input name="avatar" type="file" accept="image/jpeg,image/png,image/webp" className="mt-2 block w-full text-sm text-foreground/60 file:mr-4 file:rounded-lg file:border-0 file:bg-primary/20 file:px-4 file:py-2 file:text-primary"/></label>
          <p className="text-xs text-foreground/40">JPG, PNG or WebP · Up to 5 MB · Cropped to a square.</p>
          {profile.avatar && <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="removeAvatar" value="true"/>Remove current photo</label>}
          <button disabled={busy} className={control+" bg-primary/30"}>{busy ? "Saving…" : "Save profile"}</button>
        </form>}
        <div role="tablist" aria-label="Profile activity" className="mt-8 flex gap-2 overflow-x-auto border-b border-foreground/10">{tabs.map(t=><button role="tab" aria-selected={tab===t.key} key={t.key} onClick={()=>setTab(t.key)} className={"whitespace-nowrap border-b-2 px-4 pb-4 pt-2 text-sm "+(tab===t.key ? "border-primary text-primary" : "border-transparent text-foreground/45")}>{t.label} <span className="ml-2 text-xs opacity-60">{profile.counts[t.key]}</span></button>)}</div>
        <section role="tabpanel" className="mt-6">
          {tab==="followers" || tab==="following" ? <div className="grid gap-3 sm:grid-cols-2">{profile[tab].map(member=><Link href={`/profile/${member.id}`} key={member.id} className="flex items-center gap-4 rounded-2xl border border-foreground/10 bg-card p-5 hover:border-primary/40"><div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-primary/20 font-semibold">{member.avatar ? <img src={member.avatar} alt="" className="h-full w-full object-cover"/> : member.name.slice(0,1).toUpperCase()}</div><div><p className="font-medium">{member.name}</p><p className="mt-1 text-xs text-foreground/40">View profile →</p></div></Link>)}</div> : <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{profile[tab].map(item=><article key={item.purchaseId || item.id} className="overflow-hidden rounded-2xl border border-foreground/10 bg-card"><div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/15 to-secondary text-5xl">{item.emoji}</div><div className="p-5"><div className="flex items-start justify-between gap-3"><h2 className="font-semibold">{item.title}</h2><p className="whitespace-nowrap text-sm text-primary">{item.price} SOL</p></div><p className="mt-2 text-xs text-foreground/40">{item.type} · {item.duration}</p><p className="mt-4 text-xs uppercase tracking-wider text-emerald-300">{tab==="sold" ? "Sale completed" : tab==="bought" ? "Purchase confirmed" : item.status}</p>{item.date && <p className="mt-2 text-xs text-foreground/35">{new Date(item.date).toLocaleDateString()}</p>}</div></article>)}</div>}
          {profile[tab].length===0 && <div className="rounded-2xl border border-dashed border-foreground/10 px-6 py-14 text-center"><p className="text-lg font-medium">{tab==="followers" ? "No followers yet" : tab==="following" ? "Not following anyone yet" : tab==="sold" ? "No completed sales yet" : tab==="bought" ? "No purchases yet" : "No surfaces listed yet"}</p><Link href="/" className="mt-5 inline-block text-sm text-primary">Explore marketplace →</Link></div>}
          {profile.counts[tab]>50 && <p className="mt-4 text-xs text-foreground/40">Showing the most recent 50 entries.</p>}
        </section>
      </>}
      <footer className="mt-14 border-t border-foreground/10 py-6 text-xs text-foreground/30">AdMint</footer>
    </div>
  </main>;
}
