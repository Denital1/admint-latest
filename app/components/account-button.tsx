"use client";
import { NotificationLink } from "./notification-link";
import Link from "next/link";
import { useAuth } from "../lib/auth";
export function AccountButton() {
  const { user, loading } = useAuth();
  return <><Link href="/orders" className="notification-link">Orders & chat</Link><NotificationLink/><Link href={user ? "/profile" : "/login"} className="rounded-lg border border-foreground/15 px-3 py-2 text-xs font-medium hover:bg-foreground/10">{loading ? "Account…" : user ? "My profile" : "Log in / Sign up"}</Link></>;
}
