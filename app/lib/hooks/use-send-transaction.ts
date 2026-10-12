"use client";

import { useState, useCallback } from "react";
import { useSWRConfig } from "swr";
import type { Instruction } from "@solana/kit";
import { createClient } from "@solana/kit-client-rpc";
import { useWallet } from "../wallet/context";
import { useCluster } from "../../components/cluster-context";
import { getClusterUrl, getClusterWsConfig } from "../solana-client";

export function useSendTransaction() {
  const { signer } = useWallet();
  const { cluster } = useCluster();
  const { mutate } = useSWRConfig();
  const [isSending, setIsSending] = useState(false);

  const send = useCallback(
    async ({ instructions }: { instructions: readonly Instruction[] }) => {
      if (!signer) throw new Error("Wallet not connected");

      const sendOnce = async () => {
        // Create a fresh transaction client for every attempt.
        // This avoids reusing stale transaction/blockhash state.
        const txClient = createClient({
          url: getClusterUrl(cluster),
          rpcSubscriptionsConfig: getClusterWsConfig(cluster),
          payer: signer,
        });

        return txClient.sendTransaction([...instructions]);
      };

      setIsSending(true);

      try {
        try {
          const result = await sendOnce();

          mutate(
            (key: unknown) => Array.isArray(key) && key[0] === "balance",
          );

          return result.context.signature;
        } catch (error) {
          const message =
            error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();

          const isExpiredBlockhash =
            message.includes("last block") ||
            message.includes("blockhash") ||
            message.includes("expired");

          if (!isExpiredBlockhash) {
            throw error;
          }

          console.warn(
            "Transaction blockhash expired. Retrying with a fresh transaction...",
          );

          // One automatic retry with a completely fresh client/blockhash.
          const retryResult = await sendOnce();

          mutate(
            (key: unknown) => Array.isArray(key) && key[0] === "balance",
          );

          return retryResult.context.signature;
        }
      } finally {
        setIsSending(false);
      }
    },
    [signer, cluster, mutate],
  );

  return { send, isSending };
}
