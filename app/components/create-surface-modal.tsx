"use client";
/* eslint-disable @next/next/no-img-element -- Selected files use local object URLs for preview. */

import { FormEvent, useState, useEffect, useRef } from "react";
import type { Surface } from "../lib/api";
import { durationUnits, formatDuration, type DurationUnit } from "../lib/duration";

export type CreateSurfaceInput = Omit<
  Surface,
  | "id"
  | "price"
  | "status"
  | "sellerAddress"
  | "buyerAddress"
  | "txSignature"
  | "mintAddress"
> & { photoFile?: File };

type Props = {
  onClose: () => void;
  onCreate: (surface: CreateSurfaceInput) => Promise<void> | void;
};

export function CreateSurfaceModal({ onClose, onCreate }: Props) {
  const [type, setType] = useState<"Physical" | "Digital">("Physical");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [title,setTitle]=useState("");
  const [duration,setDuration]=useState("");
  const [durationUnit,setDurationUnit]=useState<DurationUnit>("days");
  const formattedDuration = formatDuration(duration, durationUnit);
  const [price,setPrice]=useState("");
  const [tagline,setTagline]=useState("");
  const [emoji,setEmoji]=useState("");
  const [error,setError]=useState("");
  const [photoFile,setPhotoFile]=useState<File>();
  const [photoPreview,setPhotoPreview]=useState("");
  const photoInput=useRef<HTMLInputElement>(null);
  useEffect(()=>()=>{if(photoPreview)URL.revokeObjectURL(photoPreview);},[photoPreview]);
  function choosePhoto(file?:File){
    if(file && (!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>5*1024*1024)){
      setError("Choose a JPG, PNG or WebP image up to 5 MB.");
      if(photoInput.current)photoInput.current.value="";
      return;
    }
    setError("");setPhotoFile(file);setPhotoPreview(file?URL.createObjectURL(file):"");
  }
  const dialog=useRef<HTMLDivElement>(null);
  const close=useRef(onClose);
  useEffect(()=>{close.current=onClose;},[onClose]);
  const submitting=useRef(false);
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const overflow=document.body.style.overflow;document.body.style.overflow="hidden";
    dialog.current?.querySelector<HTMLInputElement>('input')?.focus();
    function keyboard(event:KeyboardEvent){
      if(event.key==="Escape"&&!submitting.current)close.current();
      if(event.key!=="Tab")return;
      const elements=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled)')||[]);
      const first=elements[0],last=elements[elements.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
    document.addEventListener("keydown",keyboard);
    return ()=>{document.body.style.overflow=overflow;document.removeEventListener("keydown",keyboard);previous?.focus();};
  },[]);
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(submitting.current)return;

    const form = new FormData(event.currentTarget);

    const title = String(form.get("title") || "").trim();
    const duration = formatDuration(String(form.get("duration") || ""), durationUnit);
    if (!duration) {
      setError("Enter a positive duration of at least one minute after rounding.");
      return;
    }
    const rawPrice = String(form.get("price") || "").trim();
    const tagline = String(form.get("tagline") || "").trim();
    const emoji = String(form.get("emoji") || "").trim() || "✨";
    const priceSol = Number(rawPrice);

    if (!title || !duration || !Number.isFinite(priceSol) || priceSol <= 0) {
      return;
    }

    submitting.current=true;
    setError("");
    setIsSubmitting(true);
    try {
      await onCreate({
        title,
        photoFile,
        owner: "@you",
        type,
        duration,
        priceSol,
        emoji,
        tagline: tagline || "Fresh attention. Now for sale.",
        accent:
          type === "Digital"
            ? "from-sky-500/25 to-cyan-500/5"
            : "from-violet-500/30 to-fuchsia-500/5",
      });
      onClose();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not list your surface. Please try again.");
    } finally {
      submitting.current=false;
      setIsSubmitting(false);
    }
  }

  return <div className="listing-overlay" onClick={e=>{if(e.target===e.currentTarget&&!isSubmitting)onClose();}}>
    <div ref={dialog} className="listing-dialog" role="dialog" aria-modal="true" aria-labelledby="listing-heading">
      <div className="listing-editor">
        <header className="listing-heading"><div><span className="listing-eyebrow">A NEW SPACE</span><h2 id="listing-heading">List a <em>surface.</em></h2></div><button type="button" className="listing-close" aria-label="Close listing form" disabled={isSubmitting} onClick={onClose}>×</button></header>
        <form onSubmit={handleSubmit}>
          <fieldset disabled={isSubmitting}>
            <div className="listing-type" role="group" aria-label="Surface type">{(["Physical","Digital"] as const).map(value=><button type="button" key={value} aria-pressed={type===value} onClick={()=>setType(value)}><span aria-hidden="true">{value==="Physical"?"◈":"▧"}</span>{value}<span aria-hidden="true">{type===value?"✓":"↗"}</span></button>)}</div>
            <label className="listing-field" htmlFor="listing-name">Surface name<input id="listing-name" name="title" value={title} onChange={e=>setTitle(e.target.value)} required maxLength={120} placeholder="My laptop lid"/></label>
            <div className="listing-field-row"><div className="listing-field"><label htmlFor="listing-duration">Duration</label><div className="listing-duration-input"><input id="listing-duration" name="duration" value={duration} onChange={e=>{if (/^\d*(?:\.\d*)?$/.test(e.target.value)) setDuration(e.target.value);}} required inputMode="decimal" pattern="[0-9]+([.][0-9]*)?" maxLength={16} placeholder="7" aria-describedby="listing-duration-help"/><select aria-label="Duration unit" value={durationUnit} onChange={e=>setDurationUnit(e.target.value as DurationUnit)}>{durationUnits.map(unit=><option key={unit} value={unit}>{unit[0].toUpperCase()+unit.slice(1)}</option>)}</select></div><p id="listing-duration-help" className="listing-duration-help" aria-live="polite">{formattedDuration || (duration ? "Enter at least one minute after rounding." : "Decimals allowed · rounded to the nearest minute")}{(durationUnit === "months" || durationUnit === "years") && <span>1 month = 30 days · 1 year = 365 days</span>}</p></div><label className="listing-field" htmlFor="listing-price">Asking price<div className="listing-price-input"><input id="listing-price" name="price" value={price} onChange={e=>setPrice(e.target.value)} required type="number" step="0.000000001" min="0.000000001" placeholder="0.25"/><span>SOL</span></div></label></div>
            <label className="listing-field" htmlFor="listing-description">Description <span className="listing-optional">Optional</span><textarea id="listing-description" name="tagline" rows={3} maxLength={240} value={tagline} onChange={e=>setTagline(e.target.value)} placeholder="A little about your space and its audience…"/></label>
            <div className="listing-photo-field"><label className="listing-field" htmlFor="listing-photo">Surface photo <span className="listing-optional">Optional</span><input ref={photoInput} id="listing-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>choosePhoto(e.target.files?.[0])}/></label><p>JPG, PNG or WebP · up to 5 MB</p>{photoFile&&<button type="button" className="button-text" onClick={()=>{choosePhoto();if(photoInput.current)photoInput.current.value="";}}>Remove photo ×</button>}</div>
            <label className="listing-field listing-icon-field" htmlFor="listing-icon">Icon <span className="listing-optional">Optional</span><input id="listing-icon" name="emoji" maxLength={16} value={emoji} onChange={e=>setEmoji(e.target.value)} placeholder="✳"/></label>
          </fieldset>
          {error&&<p className="listing-error" role="alert">{error}</p>}
          <footer className="listing-form-footer"><button type="button" className="button-text" disabled={isSubmitting} onClick={onClose}>Cancel</button><button type="submit" className="button-solid" disabled={isSubmitting}>{isSubmitting?"Listing…":"Publish surface"}<span aria-hidden="true">{isSubmitting?"◌":"↗"}</span></button></footer>
        </form>
      </div>
      <aside className="listing-preview" aria-label="Listing preview">
        <div className="listing-preview-top"><span>LIVE PREVIEW</span><span aria-hidden="true">↗</span></div>
        <div className="listing-preview-art">{photoPreview?<img className="listing-upload-preview" src={photoPreview} alt="Your surface preview"/>:<><div className="listing-preview-orbit"/><div className="listing-paper"><span>{type==="Physical"?"IN THE REAL WORLD":"ON THE SCREEN"}</span><div aria-hidden="true">{emoji||"✳"}</div><b>Your space.<br/><em>Their next idea.</em></b><footer>AD SPACE <span>001 / ∞</span></footer></div></>}</div>
        <div className="listing-preview-detail"><span className="listing-preview-category">{type} surface</span><h3>{title.trim()||"Your next great space"}</h3><p>{tagline.trim()||"Make room for a new brand."}</p><div className="listing-preview-price"><span>{price&&Number(price)>0?price:"0.00"}<small>SOL</small></span><span>{formattedDuration||"Your duration"}</span></div></div>
        <div className="listing-payment"><span aria-hidden="true">↙</span><p>Payment goes directly to your<br/><strong>connected wallet.</strong></p></div>
      </aside>
    </div>
  </div>;
}
