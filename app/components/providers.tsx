"use client";

import { TransactionProvider } from "./transaction-progress";
import { Appearance } from "./appearance";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { PropsWithChildren } from "react";
import { ClusterProvider } from "./cluster-context";
import { AuthProvider } from "../lib/auth";
import { WalletProvider } from "../lib/wallet/context";
import { SolanaClientProvider } from "../lib/solana-client-context";

export function Providers({ children }: PropsWithChildren) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark">
      <ClusterProvider>
        <SolanaClientProvider>
          <WalletProvider><AuthProvider><TransactionProvider>{children}</TransactionProvider></AuthProvider></WalletProvider>
        </SolanaClientProvider>
        <Appearance />
        <Toaster position="bottom-right" richColors />
      </ClusterProvider>
    </ThemeProvider>
  );
}
