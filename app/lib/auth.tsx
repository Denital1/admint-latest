"use client";
import { createContext, useContext, useEffect, useState, useCallback, type PropsWithChildren } from "react";
import { useWallet } from "./wallet/context";

type User = { id: number; name: string; email: string; wallets: string[] };
export async function authRequest(path: string, data?: unknown) {
  let csrfToken = "";
  if (data !== undefined) {
    const initial = await fetch("/api/auth/session/", { credentials: "include", cache: "no-store" });
    if (!initial.ok) throw new Error("Cannot connect to the login service.");
    csrfToken = (await initial.json()).csrfToken;
  }
  const response = await fetch(`/api/auth/${path}/`, {
    method: data === undefined ? "GET" : "POST", credentials: "include", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail || "Unable to sign in. Please refresh and try again.");
  return result;
}
type AuthContextType = { user: User | null; loading: boolean; googleEnabled: boolean; refresh: () => Promise<void>; signOut: () => Promise<void>; signInPhantom: () => Promise<void> };
const AuthContext = createContext<AuthContextType | null>(null);
export function AuthProvider({ children }: PropsWithChildren) {
  const { wallet, connectors, connect, disconnect } = useWallet();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const refresh = useCallback(async () => {
    const data = await authRequest("session");
    setUser(data.user); setGoogleEnabled(data.googleEnabled); setLoading(false);
  }, []);
  useEffect(() => { let active = true; authRequest("session").then((data) => { if (active) { setUser(data.user); setGoogleEnabled(data.googleEnabled); setLoading(false); } }).catch(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  async function signOut() {
    await authRequest("logout", {}); setUser(null); await disconnect();
  }
  async function signInPhantom() {
    const phantom = connectors.find((c) => c.name.toLowerCase().includes("phantom"));
    if (!phantom) throw new Error("Open this page in Chrome with the Phantom extension installed and unlocked.");
    const session = wallet?.connector.id === phantom.id ? wallet : await connect(phantom.id);
    if (!session.signMessage) throw new Error("This wallet does not support message signing.");
    const challenge = await authRequest("wallet/challenge", { wallet: session.account.address });
    const signed = await session.signMessage(new TextEncoder().encode(challenge.message));
    const signature = btoa(Array.from(signed, (byte) => String.fromCharCode(byte)).join(""));
    const result = await authRequest("wallet/verify", { challenge: challenge.challenge, signature });
    setUser(result.user);
  }
  return <AuthContext.Provider value={{ user, loading, googleEnabled, refresh, signOut, signInPhantom }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing.");
  return value;
}
