"use client";
import Link from "next/link";
import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { authRequest, useAuth } from "../lib/auth";

export default function LoginPage() { return <Suspense fallback={<main className="min-h-screen bg-background p-12 text-foreground">Loading sign-in…</main>}><LoginForm /></Suspense>; }
function LoginForm() {
  const { user, loading, googleEnabled, refresh, signOut, signInPhantom } = useAuth();
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reason = useSearchParams().get("error");
  const displayedError = error || (reason ? reason === "google_not_configured" ? "Google sign-in is waiting for the project owner's OAuth configuration." : "Google sign-in was cancelled or could not be verified. Please try again." : "");
  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); } catch (err) { setError(err instanceof Error ? err.message : "Sign-in failed."); } finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const fields = new FormData(event.currentTarget);
    await run(async () => {
      await authRequest(signup ? "signup" : "login", { email: fields.get("email"), password: fields.get("password"), name: fields.get("name") });
      await refresh();
    });
  }
  const button = "w-full rounded-xl border border-foreground/15 px-4 py-3 text-sm font-medium transition hover:bg-foreground/10 disabled:opacity-50 disabled:cursor-not-allowed";
  const input = "w-full rounded-xl border border-foreground/15 bg-foreground/5 px-4 py-3 text-sm outline-none focus:border-primary";
  return <main className="min-h-screen bg-background px-5 py-12 text-foreground">
    <div className="mx-auto max-w-md">
      <Link href="/" className="text-sm text-foreground/60 hover:text-foreground">← Back to marketplace</Link>
      <section className="mt-8 rounded-3xl border border-foreground/10 bg-card p-7 shadow-2xl">
        <div className="mb-7 text-xl font-bold">AdMint<span className="text-primary">.</span></div>
        <h1 className="text-3xl font-semibold">{user ? "Your account" : signup ? "Create your account" : "Welcome back"}</h1>
        <p className="mt-2 text-sm leading-6 text-foreground/50">{user ? "Manage your sign-in and connected wallet." : "Sign in to AdMint."}</p>
        {displayedError && <div role="alert" className="mt-5 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">{displayedError}</div>}
        {loading ? <p className="mt-6" role="status">Loading your session…</p> : user ? <div className="mt-6 space-y-4">
          <div className="rounded-xl bg-foreground/5 p-4"><p className="font-medium">{user.name}</p>{user.email && <p className="mt-1 break-all text-sm text-foreground/60">{user.email}</p>}
          {user.wallets.map((wallet) => <p key={wallet} className="mt-3 break-all font-mono text-xs text-primary">Phantom: {wallet}</p>)}</div>
          <button disabled={busy} onClick={() => run(signInPhantom)} className={button}>{busy ? "Waiting for wallet…" : "Link / verify Phantom wallet"}</button>
          <Link href="/" className="block rounded-xl bg-primary text-primary-foreground px-4 py-3 text-center text-sm font-semibold hover:bg-primary/90">Explore marketplace →</Link>
          <button disabled={busy} onClick={() => run(signOut)} className={button}>Log out</button>
        </div> : <>
          <div className="mt-6 space-y-3">
            <button disabled={busy} onClick={() => run(signInPhantom)} className={button}>{busy ? "Please wait…" : "Continue with Phantom"}</button>
            <p className="text-xs leading-5 text-foreground/45">Approve a sign-in message in Phantom. No payment or transaction is required. New wallets get an account automatically.</p>
            <button disabled={busy || !googleEnabled} onClick={() => { window.location.assign("/api/auth/google/start/"); }} className={button}>Continue with Google</button>
            {!googleEnabled && <p className="text-xs leading-5 text-foreground/45">Google sign-in is not configured yet.</p>}
          </div>
          <div className="my-6 flex items-center gap-3 text-xs text-foreground/40"><span className="h-px flex-1 bg-foreground/10"/>or continue with email<span className="h-px flex-1 bg-foreground/10"/></div>
          <form onSubmit={submit} className="space-y-4">
            {signup && <label className="block text-sm">Name<input name="name" autoComplete="name" required maxLength={80} className={input + " mt-2"}/></label>}
            <label className="block text-sm">Email<input name="email" type="email" autoComplete="email" required maxLength={254} className={input + " mt-2"}/></label>
            <label className="block text-sm">Password<input name="password" type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 10 : 1} maxLength={128} className={input + " mt-2"}/></label>
            {signup && <p className="text-xs text-foreground/45">At least 10 characters. Avoid common passwords.</p>}
            <button disabled={busy} className="w-full rounded-xl bg-primary text-primary-foreground px-4 py-3 text-sm font-semibold hover:bg-primary/90 disabled:opacity-50">{busy ? "Please wait…" : signup ? "Create account" : "Log in"}</button>
          </form>
          <button disabled={busy} onClick={() => { setSignup(!signup); setError(""); }} className="mt-5 w-full text-sm text-primary hover:text-primary">{signup ? "Already have an account? Log in" : "New to AdMint? Sign up"}</button>
        </>}
      </section>
    </div>
  </main>;
}
