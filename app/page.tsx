"use client";
/* eslint-disable @next/next/no-img-element -- Database images and private evidence use session-aware native requests. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ProfileSearch } from "./components/profile-search";
import { toast } from "sonner";
import { ClusterSelect } from "./components/cluster-select";
import { AccountButton } from "./components/account-button";
import { WalletButton } from "./components/wallet-button";
import { useAuth } from "./lib/auth";
import { useWallet } from "./lib/wallet/context";
import {
  CreateSurfaceModal,
  type CreateSurfaceInput,
} from "./components/create-surface-modal";
import { BuyRightsButton } from "./components/buy-rights-button";
import { createListing, getListings, type Surface } from "./lib/api";

const initialSurfaces: Surface[] = [
  {
    id: -1,
    title: "Hackathon Laptop Lid",
    owner: "@giorgi",
    type: "Physical",
    duration: "Until demo ends",
    price: "0.25 SOL",
    priceSol: 0.25,
    emoji: "💻",
    tagline: "Your logo. My laptop. Everyone stares.",
    accent: "from-violet-500/30 to-fuchsia-500/5",
  },
  {
    id: -2,
    title: "@creator X Banner",
    owner: "@creator",
    type: "Digital",
    duration: "7 days",
    price: "0.80 SOL",
    priceSol: 0.8,
    emoji: "𝕏",
    tagline: "Rent the first thing my followers see.",
    accent: "from-sky-500/25 to-cyan-500/5",
  },
  {
    id: -3,
    title: "Garage Wall",
    owner: "@houseowner",
    type: "Physical",
    duration: "30 days",
    price: "2.50 SOL",
    priceSol: 2.5,
    emoji: "🏠",
    tagline: "A blank wall is just wasted inventory.",
    accent: "from-orange-500/20 to-amber-500/5",
  },
  {
    id: -4,
    title: "Hoodie Front",
    owner: "@builder",
    type: "Physical",
    duration: "Tonight only",
    price: "0.15 SOL",
    priceSol: 0.15,
    emoji: "👕",
    tagline: "Yes. The hoodie is monetizable.",
    accent: "from-pink-500/25 to-rose-500/5",
  },
  {
    id: -5,
    title: "Stream Overlay",
    owner: "@streamer",
    type: "Digital",
    duration: "24 hours",
    price: "0.40 SOL",
    priceSol: 0.4,
    emoji: "🎥",
    tagline: "Own a piece of the live screen.",
    accent: "from-emerald-500/20 to-teal-500/5",
  },
  {
    id: -6,
    title: "Conference Badge Back",
    owner: "@attendee",
    type: "Physical",
    duration: "1 event day",
    price: "0.10 SOL",
    priceSol: 0.1,
    emoji: "🎫",
    tagline: "If people can see it, it can be inventory.",
    accent: "from-indigo-500/25 to-violet-500/5",
  },
];

export default function Home() {
  const { wallet } = useWallet();
  const {user} = useAuth();
  const [category,setCategory]=useState("All surfaces");
  const [view,setView]=useState<"available"|"sold">("available");
  const [visibleCount,setVisibleCount]=useState(12);
  const [query,setQuery]=useState("");
  const [maxPrice,setMaxPrice]=useState("");
  const [location,setLocation]=useState("");
  const [sort,setSort]=useState("newest");
  const [surfaces, setSurfaces] = useState<Surface[]>(initialSurfaces);
  const [isListingOpen, setIsListingOpen] = useState(false);
  const [isLoadingListings, setIsLoadingListings] = useState(true);

  useEffect(() => {
    let active = true;

    void getListings()
      .then((listings) => {
        if (active) {
          setSurfaces(listings);
          const target = listings.find(item => `#surface-${item.id}` === window.location.hash);
          if (target) {
            const selected = target.status === "sold" ? "sold" : "available";
            setView(selected);
            const position = listings.filter(item => selected === "sold" ? item.status === "sold" : item.status !== "sold").findIndex(item => item.id === target.id);
            setVisibleCount(Math.max(12, position + 1));
            requestAnimationFrame(() => document.getElementById(`surface-${target.id}`)?.scrollIntoView({block:"center"}));
          }
        }
      })
      .catch((error) => {
        console.warn("AdMint API unavailable; using local showcase data.", error);
      })
      .finally(() => {
        if (active) setIsLoadingListings(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const createSurface = async (surface: CreateSurfaceInput) => {
    if (!wallet) {
      toast.error("Connect your wallet before listing a surface.");
      throw new Error("Connect your wallet before listing a surface.");
    }

    try {
      const created = await createListing({
        title: surface.title,
        owner: surface.owner,
        surfaceType: surface.type,
        duration: surface.duration,
        priceSol: surface.priceSol,
        emoji: surface.emoji,
        tagline: surface.tagline,
        accent: surface.accent,
        sellerWallet: wallet.account.address,
        photoFile: surface.photoFile,
      });
      setSurfaces((current) => [created, ...current]);
      toast.success("Surface listed successfully.", {action:{label:"Add photos & details",onClick:()=>window.location.assign(`/listing/${created.id}`)}});
    } catch (error) {
      toast.error("Could not create listing.", {
        description: error instanceof Error ? error.message : "API error",
      });
      throw error;
    }
  };

  const markSurfaceSold = (
    listingId: number,
    signature: string,
    buyerAddress: string,
  ) => {
    setSurfaces((current) =>
      current.map((surface) =>
        surface.id === listingId
          ? {
              ...surface,
              status: "sold",
              buyerAddress,
              txSignature: signature,
            }
          : surface,
      ),
    );
  };


  const activeSurfaces=surfaces.filter(s=>s.status!=="sold");
  const soldSurfaces=surfaces.filter(s=>s.status==="sold");
  const sectionSurfaces=view==="sold"?soldSurfaces:activeSurfaces;
  const filtered=sectionSurfaces.filter(s=>(category==="All surfaces" || s.type===category) && (!maxPrice||s.priceSol<=Number(maxPrice)) && (!location||(s.location||"").toLowerCase().includes(location.toLowerCase())) && `${s.title} ${s.owner} ${s.tagline}`.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==="low"?a.priceSol-b.priceSol:sort==="high"?b.priceSol-a.priceSol:0);
  function changeView(next:"available"|"sold"){setView(next);setVisibleCount(12);}
  function openListing(){if(!user){toast.info("Log in to list your surface.");window.location.assign("/login");return;}setIsListingOpen(true);}
  return <div className="market-shell">
    <aside className="market-sidebar">
      <Link href="/" className="brand">ad<span>mint</span></Link>
      <nav aria-label="Main navigation"><button className="sidebar-section-link" aria-pressed={view==="available"} onClick={()=>changeView("available")}><span>◈</span> Discover <i>↗︎</i></button><button className="sidebar-section-link" aria-pressed={view==="sold"} onClick={()=>changeView("sold")}><span>✓</span> Sold <i>{soldSurfaces.length}</i></button><Link href="/profile"><span>◯</span> My profile</Link><Link href="/notifications"><span>♧</span> Notifications</Link><Link href="/orders"><span>▤</span> Orders & chat</Link><Link href="/saved"><span>♡</span> Saved</Link></nav>
      <button className="button-solid sidebar-list" onClick={openListing}>List a surface <span>＋</span></button>
      <div className="sidebar-bottom"><span className="status-dot"/> Built on Solana <span>↗︎</span></div>
    </aside>
    <main className="market-main">
      <header className="market-header"><Link href="/" className="brand mobile-brand">ad<span>mint</span></Link><div className="header-breadcrumb">Marketplace <span> / </span><b>Discover</b></div><div className="header-actions"><ClusterSelect/><AccountButton/><WalletButton/></div></header>
      <div className="market-content">
        <section className="editorial-hero">
          <div className="hero-copy"><h1>Space for<br/>your <em>brand.</em></h1><p className="hero-description">Buy and sell advertising space.</p><div className="hero-actions"><button className="button-solid" onClick={()=>document.getElementById("marketplace")?.scrollIntoView({behavior:"smooth"})}>Browse surfaces <span>↗︎</span></button><button className="button-text" onClick={openListing}>List a surface <span>＋</span></button></div></div>
          <div className="hero-art" aria-label="Illustration of a tokenized advertising space"><div className="art-grid"/><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="art-token"><span>ad</span><b>↗︎</b></div><div className="art-ticket"><span>AD SPACE</span><b>001 / ∞</b><i>✳︎</i></div><span className="art-corner">✳︎</span></div>
        </section>
        <section id="marketplace" className="marketplace-section">
          <div className="section-heading"><div><h2>{view==="sold"?"Sold surfaces":"Surfaces"}</h2></div><span className="collection-count">{isLoadingListings?"Loading…":`${sectionSurfaces.length} listings`}</span></div>
          <ProfileSearch/>
          <div className="archive-tabs" role="group" aria-label="Marketplace section"><button aria-pressed={view==="available"} onClick={()=>changeView("available")}>Marketplace <span>{activeSurfaces.length}</span></button><button aria-pressed={view==="sold"} onClick={()=>changeView("sold")}>Sold <span>{soldSurfaces.length}</span></button></div>
          <div className="collection-tools"><div className="filter-tabs" role="group" aria-label="Surface category">{["All surfaces","Physical","Digital"].map(c=><button key={c} aria-pressed={category===c} onClick={()=>{setCategory(c);setVisibleCount(12);}}>{c}{c==="All surfaces"&&<span>{sectionSurfaces.length}</span>}</button>)}</div><div className="search-sort"><label className="market-search"><span aria-hidden="true">⌕</span><input type="search" aria-label="Search surfaces" placeholder="Search surfaces…" value={query} onChange={e=>{setQuery(e.target.value);setVisibleCount(12);}}/></label><select aria-label="Sort surfaces" value={sort} onChange={e=>{setSort(e.target.value);setVisibleCount(12);}}><option value="newest">Newest first</option><option value="low">Price: low to high</option><option value="high">Price: high to low</option></select></div></div>
          <div className="discovery-filters"><label>Location<input aria-label="Filter by location" value={location} onChange={e=>{setLocation(e.target.value);setVisibleCount(12);}} placeholder="Any location"/></label><label>Max price · SOL<input aria-label="Maximum price in SOL" type="number" min="0" value={maxPrice} onChange={e=>{setMaxPrice(e.target.value);setVisibleCount(12);}} placeholder="Any price"/></label><Link href="/saved">♡ Saved surfaces</Link></div>
          <div className="surface-grid">{filtered.slice(0,visibleCount).map((surface,index)=><article className="surface-card" id={`surface-${surface.id}`} key={surface.id}>
            <div className={`surface-art surface-art-${index%4}`}><span className="surface-kind">{surface.type} <span>↗︎</span></span>{surface.photo?<img className="surface-real-photo" src={surface.photo} alt={surface.title}/>:<SurfaceArtwork title={surface.title} type={surface.type}/>}<span className="surface-number">{String(index+1).padStart(2,"0")}</span></div>
            <div className="surface-info"><div className="surface-title-row"><h3><Link className="surface-detail-link" href={`/listing/${surface.id}`} aria-label={`View ${surface.title} details`}>{surface.title}</Link></h3><span className="surface-price">{surface.priceSol}<small>SOL</small></span></div><p className="surface-owner">by {surface.sellerAddress?<Link href={`/profile/wallet/${encodeURIComponent(surface.sellerAddress)}`}>{surface.owner} <span>↗︎</span></Link>:surface.owner}</p><p className="surface-description">{surface.tagline}</p>{view==="sold"&&surface.buyerAddress&&<p className="surface-owner sold-buyer">Bought by <Link href={`/profile/wallet/${encodeURIComponent(surface.buyerAddress)}`}>{surface.buyerAddress.slice(0,4)}…{surface.buyerAddress.slice(-4)} ↗︎</Link></p>}<div className="surface-footer"><span className="surface-duration">◷ {surface.duration}</span><BuyRightsButton listingId={surface.id} sellerAccountId={surface.ownerAccountId} sellerAddress={surface.sellerAddress} price={surface.price} sold={surface.status==="sold"} reserved={surface.status==="reserved"} txSignature={surface.txSignature} onReconciled={async()=>setSurfaces(await getListings())} onPurchased={(signature,buyerAddress)=>markSurfaceSold(surface.id,signature,buyerAddress)}/></div></div>
          </article>)}</div>
          {filtered.length>visibleCount&&<div className="archive-more"><button className="button-solid" onClick={()=>setVisibleCount(n=>n+12)}>Show more <span>＋</span></button><p>{Math.min(visibleCount,filtered.length)} of {filtered.length}</p></div>}
          {filtered.length===0&&<div className="collection-empty"><h3>{view==="sold"&&!query&&category==="All surfaces"?"No sales yet":"No results"}</h3><p>{view==="sold"&&!query&&category==="All surfaces"?"Completed sales will appear here.":"Try a different search."}</p><button className="button-text" onClick={()=>{setQuery("");setCategory("All surfaces");setLocation("");setMaxPrice("");}}>Clear filters ↗︎</button></div>}
        </section>
        <footer className="market-footer"><Link className="brand" href="/">ad<span>mint</span></Link><Link href="/profile">My profile ↗︎</Link><span>© {new Date().getFullYear()} AdMint</span></footer>
      </div>
    </main>
    {isListingOpen&&<CreateSurfaceModal onClose={()=>setIsListingOpen(false)} onCreate={createSurface}/>}
  </div>;
}

function SurfaceArtwork({title,type}:{title:string;type:string}){
  const name=title.toLowerCase();
  if(name.includes("hoodie"))return <svg className="object-art" viewBox="0 0 260 180" aria-hidden="true"><path d="M99 48Q100 16 130 16Q160 16 161 48L191 61L218 127L187 140L169 104L173 170H87L91 104L73 140L42 127L69 61Z" fill="currentColor"/><path d="M103 49Q130 70 157 49M130 68V110M108 137H152" fill="none" stroke="var(--art-paper)" strokeWidth="2"/><text x="130" y="124" textAnchor="middle" fill="var(--art-paper)" fontSize="20" fontFamily="Georgia">your brand.</text></svg>;
  if(name.includes("badge"))return <svg className="object-art object-tilt" viewBox="0 0 260 180" aria-hidden="true"><path d="M105 0L123 44M155 0L137 44" stroke="currentColor" strokeWidth="9"/><rect x="76" y="38" width="108" height="136" rx="12" fill="var(--art-paper)" stroke="currentColor" strokeWidth="2"/><path d="M116 53H144" stroke="currentColor" strokeWidth="5" strokeLinecap="round"/><text x="130" y="104" fontFamily="Georgia" fontSize="35" textAnchor="middle" fill="currentColor">hello.</text><text x="130" y="127" fontSize="8" letterSpacing="2" textAnchor="middle" fill="currentColor">YOUR BRAND HERE</text><path d="M97 148H163" stroke="currentColor" strokeWidth="2" strokeDasharray="2 3"/></svg>;
  if(type==="Digital")return <svg className="object-art" viewBox="0 0 260 180" aria-hidden="true"><rect x="24" y="25" width="212" height="134" rx="9" fill="var(--art-paper)" stroke="currentColor" strokeWidth="2"/><path d="M24 48H236" stroke="currentColor" strokeWidth="1"/><circle cx="37" cy="37" r="2" fill="currentColor"/><circle cx="45" cy="37" r="2" fill="currentColor"/><circle cx="53" cy="37" r="2" fill="currentColor"/><rect x="39" y="65" width="182" height="75" rx="3" fill="currentColor"/><text x="130" y="111" textAnchor="middle" fontFamily="Georgia" fontStyle="italic" fontSize="27" fill="var(--art-paper)">made you look.</text></svg>;
  if(name.includes("wall"))return <svg className="object-art" viewBox="0 0 260 180" aria-hidden="true"><path d="M16 160H244M37 160V27H223V160M37 59H223M37 92H223M37 125H223M79 27V59M171 27V59M124 59V92M79 92V125M171 92V125M124 125V160" fill="none" stroke="currentColor" strokeWidth="1" opacity=".45"/><rect x="64" y="53" width="132" height="84" fill="var(--art-paper)" stroke="currentColor" strokeWidth="2"/><text x="130" y="102" textAnchor="middle" fontFamily="Georgia" fontStyle="italic" fontSize="26" fill="currentColor">think bigger.</text></svg>;
  return <svg className="object-art object-tilt" viewBox="0 0 260 180" aria-hidden="true"><rect x="44" y="21" width="172" height="116" rx="9" fill="currentColor"/><rect x="50" y="27" width="160" height="104" rx="5" fill="var(--art-paper)"/><path d="M44 138H216L243 159Q242 167 230 167H30Q18 167 17 159Z" fill="currentColor"/><path d="M107 145H153L160 154H100Z" fill="var(--art-paper)" opacity=".55"/><circle cx="130" cy="78" r="30" fill="currentColor"/><text x="130" y="85" fontFamily="Georgia" fontStyle="italic" fontSize="21" textAnchor="middle" fill="var(--art-paper)">ad.</text></svg>;
}
