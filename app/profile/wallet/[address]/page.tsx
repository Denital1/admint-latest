"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ProfileView } from "../../../components/profile-view";
export default function WalletProfilePage() {
  const {address} = useParams<{address: string}>();
  const [id, setId] = useState<string>();
  const [error, setError] = useState("");
  useEffect(() => { let active = true; fetch(`/api/profiles/wallet/${encodeURIComponent(address)}/`).then(async (r) => {
    if (!r.ok) throw new Error("This wallet has not created a profile yet.");
    const data = await r.json(); if (active) setId(String(data.id));
  }).catch((e) => {if (active) setError(e.message);}); return () => {active = false;}; }, [address]);
  if (id) return <ProfileView profileId={id}/>;
  return <main className="min-h-screen bg-[#0b0b10] p-12 text-white"><Link href="/">← Marketplace</Link><p className="mt-8">{error || "Loading profile…"}</p></main>;
}
