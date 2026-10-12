"use client";

import {
  Connection,
  LAMPORTS_PER_SOL,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction,
  VersionedTransaction,
} from "@solana/web3.js";
import {
  ACCOUNT_SIZE,
  AuthorityType,
  MINT_SIZE,
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccountInstruction,
  createInitializeMintInstruction,
  createMintToInstruction,
  createSetAuthorityInstruction,
  getAssociatedTokenAddressSync,
} from "@solana/spl-token";
import { toast } from "sonner";
import { getBase58Decoder } from "@solana/kit";
import { decodePendingPurchase, purchaseLamports } from "../lib/purchase-recovery";
import { useTransaction } from "./transaction-progress";

import {
  cancelPurchase,
  confirmPurchase,
  getMyPurchases,
  preparePurchase,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { useWallet } from "../lib/wallet/context";
import { useCluster } from "./cluster-context";
import { getClusterUrl } from "../lib/solana-client";

type Props = {
  listingId: number;
  sellerAccountId?: number;
  sellerAddress?: string;
  price: string;
  sold?: boolean;
  reserved?: boolean;
  txSignature?: string;
  onPurchased: (signature: string, buyerAddress: string) => void;
  onReconciled: () => Promise<void>;
};

async function waitForConfirmation(
  connection: Connection,
  signature: string,
) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const status = await connection.getSignatureStatus(signature, {
      searchTransactionHistory: true,
    });

    if (status.value?.err) {
      throw new Error("Transaction failed on-chain.");
    }

    if (
      status.value?.confirmationStatus === "confirmed" ||
      status.value?.confirmationStatus === "finalized"
    ) {
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error("Transaction was sent but confirmation is taking too long.");
}

export function BuyRightsButton({
  listingId,
  sellerAccountId,
  sellerAddress,
  price,
  sold,
  reserved,
  txSignature,
  onPurchased,
  onReconciled,
}: Props) {
  const { wallet, status } = useWallet();
  const { user } = useAuth();
  const transaction = useTransaction();
  const ownSurface = !!user && (sellerAccountId === user.id || (!!sellerAddress && user.wallets.includes(sellerAddress)));
  const { cluster, getExplorerUrl } = useCluster();
  const recoveryKey = `admint:purchase:${cluster}:${wallet?.account.address || ""}:${listingId}`;
  function pendingPurchase(): { id: number; signature: string; mint: string } | null {
    if (typeof window === "undefined" || !wallet) return null;
    try {
      return decodePendingPurchase(localStorage.getItem(recoveryKey));
    } catch { return null; }
  }
  const recovery = pendingPurchase();

  async function finishRecoveryIfTerminal() {
    if (!recovery || !wallet) return false;
    const purchases = await getMyPurchases(wallet.account.address);
    const purchase = purchases.find(item => item.id === recovery.id);
    if (!purchase || purchase.status === "pending") return false;
    if (purchase.tx_signature && purchase.tx_signature !== recovery.signature) {
      throw new Error("The saved transaction does not match this purchase. Contact support before paying again.");
    }
    localStorage.removeItem(recoveryKey);
    if (purchase.status === "confirmed") {
      transaction.advance("success");
      onPurchased(recovery.signature, wallet.account.address);
    } else {
      transaction.advance("error", {
        signature: undefined, explorer: undefined,
        error: purchase.verification_message || "This attempt was not completed. You can try purchasing again.",
      });
      // Refresh the listing and button after the API has safely released it.
      await onReconciled();
    }
    return true;
  }

  async function resumePurchase() {
    if (!recovery || !wallet || !user?.wallets.includes(wallet.account.address)) {
      toast.error("Log in with the verified buyer wallet to resume this purchase.");
      return;
    }
    if (!transaction.start(price)) return;
    try {
      transaction.advance("confirm", { signature: recovery.signature, explorer: getExplorerUrl(`/tx/${recovery.signature}`) });
      if (await finishRecoveryIfTerminal()) return;
      transaction.advance("save");
      await confirmPurchase(recovery.id, { txSignature: recovery.signature, mintAddress: recovery.mint, cluster });
      try { localStorage.removeItem(recoveryKey); } catch { /* Confirmation is already persisted by the API. */ }
      transaction.advance("success");
      onPurchased(recovery.signature, wallet.account.address);
    } catch (error) {
      // Verification can settle a failed attempt even when its HTTP response is an error.
      try { if (await finishRecoveryIfTerminal()) return; } catch { /* Keep recovery until the server can be read. */ }
      transaction.advance("error", { signature: recovery.signature, explorer: getExplorerUrl(`/tx/${recovery.signature}`), error: error instanceof Error ? error.message : "Retry confirmation later." });
    }
  }

  if (recovery && !sold) {
    return <button onClick={resumePurchase} disabled={transaction.active} className="button-solid">Resume confirmation →</button>;
  }

  if (sold) {
    return txSignature ? (
      <a
        href={getExplorerUrl(`/tx/${txSignature}`)}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.08] px-3 py-2 text-xs font-medium text-emerald-300"
      >
        SOLD ✓ ↗
      </a>
    ) : (
      <span className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.08] px-3 py-2 text-xs font-medium text-emerald-300">
        SOLD ✓
      </span>
    );
  }

  if (reserved) {
    return (
      <span className="rounded-lg border border-amber-400/20 bg-amber-400/[0.08] px-3 py-2 text-xs font-medium text-amber-300">
        RESERVED
      </span>
    );
  }

  if (ownSurface) {
    return <span className="rounded-lg border border-foreground/10 px-3 py-2 text-xs text-foreground/40">Your surface</span>;
  }

  async function handleBuy() {
    if (status !== "connected" || !wallet) {
      toast.error("Connect your wallet first.");
      return;
    }

    if (!user?.wallets.includes(wallet.account.address)) {
      toast.error("Log in and verify this wallet on your account page first.");
      return;
    }

    if (!sellerAddress) {
      toast.info("This is a showcase listing. Create your own listing to test purchases.");
      return;
    }

    if (wallet.account.address === sellerAddress) {
      toast.error("You cannot buy your own surface.");
      return;
    }

    if (!wallet.signTransaction) {
      toast.error("Wallet does not support Solana transaction signing.");
      return;
    }

    const numericPrice = Number(price.replace("SOL", "").trim());

    if (!Number.isFinite(numericPrice) || numericPrice <= 0) {
      toast.error("Invalid listing price.");
      return;
    }

    if (!transaction.start(price)) return;

    let purchaseId: number | undefined;
    let signature: string | undefined;
    let broadcastAttempted = false;
    let mintAddress: string | undefined;

    try {
      const purchase = await preparePurchase(
        listingId,
        wallet.account.address,
        cluster,
      );
      purchaseId = purchase.id;

      const connection = new Connection(getClusterUrl(cluster), "confirmed");
      const buyer = new PublicKey(wallet.account.address);
      const seller = new PublicKey(sellerAddress);

      const mintSeed = crypto.randomUUID().replace(/-/g, "").slice(0, 32);
      const mintPublicKey = await PublicKey.createWithSeed(
        buyer,
        mintSeed,
        TOKEN_PROGRAM_ID,
      );

      const priceLamports = purchaseLamports(purchase.price_sol);
      mintAddress = mintPublicKey.toBase58();
      const mintRent = await connection.getMinimumBalanceForRentExemption(
        MINT_SIZE,
      );
      const tokenAccountRent =
        await connection.getMinimumBalanceForRentExemption(ACCOUNT_SIZE);
      const buyerBalance = await connection.getBalance(buyer, "confirmed");
      const buyerTokenAccount = getAssociatedTokenAddressSync(
        mintPublicKey,
        buyer,
      );

      const latest = await connection.getLatestBlockhash("confirmed");
      const tx = new Transaction({
        feePayer: buyer,
        recentBlockhash: latest.blockhash,
      });

      // 1. Pay the seller.
      tx.add(
        SystemProgram.transfer({
          fromPubkey: buyer,
          toPubkey: seller,
          lamports: priceLamports,
        }),
      );

      // 2. Create the unique mint account.
      tx.add(
        SystemProgram.createAccountWithSeed({
          fromPubkey: buyer,
          newAccountPubkey: mintPublicKey,
          basePubkey: buyer,
          seed: mintSeed,
          lamports: mintRent,
          space: MINT_SIZE,
          programId: TOKEN_PROGRAM_ID,
        }),
      );

      // 3. Initialize it as a 0-decimal token.
      tx.add(
        createInitializeMintInstruction(
          mintPublicKey,
          0,
          buyer,
          null,
          TOKEN_PROGRAM_ID,
        ),
      );

      // 4. Create the buyer token account.
      tx.add(
        createAssociatedTokenAccountInstruction(
          buyer,
          buyerTokenAccount,
          buyer,
          mintPublicKey,
        ),
      );

      // 5. Mint exactly one Ad Right.
      tx.add(
        createMintToInstruction(
          mintPublicKey,
          buyerTokenAccount,
          buyer,
          1,
        ),
      );

      // 6. Make the one-token supply permanently fixed.
      tx.add(
        createSetAuthorityInstruction(
          mintPublicKey,
          buyer,
          AuthorityType.MintTokens,
          null,
        ),
      );

      // Bind this payment to its prepared purchase so another order cannot reuse it.
      tx.add(new TransactionInstruction({
        programId: new PublicKey("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"),
        keys: [{ pubkey: buyer, isSigner: true, isWritable: false }],
        data: Buffer.from(`AdMint purchase:${purchase.id}`, "utf8"),
      }));

      const estimatedFee =
        (await connection.getFeeForMessage(tx.compileMessage(), "confirmed"))
          .value ?? 0;
      const estimatedTotal =
        priceLamports + mintRent + tokenAccountRent + estimatedFee;

      if (buyerBalance < estimatedTotal) {
        throw new Error(
          `Not enough SOL. You have ${(buyerBalance / LAMPORTS_PER_SOL).toFixed(4)} SOL but need about ${(estimatedTotal / LAMPORTS_PER_SOL).toFixed(4)} SOL.`,
        );
      }

      const simulation = await connection.simulateTransaction(
        new VersionedTransaction(tx.compileMessage()),
        {
          commitment: "confirmed",
          sigVerify: false,
          replaceRecentBlockhash: true,
        },
      );

      if (simulation.value.err) {
        throw new Error(
          `Transaction simulation failed: ${JSON.stringify(simulation.value.err)}`,
        );
      }

      const freshLatest = await connection.getLatestBlockhash("confirmed");
      tx.recentBlockhash = freshLatest.blockhash;
      tx.feePayer = buyer;

      const unsignedBytes = tx.serialize({
        requireAllSignatures: false,
        verifySignatures: false,
      });

      transaction.advance("wallet");

      const signedBytes = await wallet.signTransaction(
        unsignedBytes,
        `solana:${cluster}`,
      );

      const signedTransaction = Transaction.from(signedBytes);
      if (!signedTransaction.signature) throw new Error("The wallet returned an unsigned transaction.");
      // Wallet unlock/approval can outlast the blockhash. Check before any broadcast.
      if (signedTransaction.recentBlockhash !== freshLatest.blockhash) {
        throw new Error("The wallet changed the transaction blockhash. No payment was sent. Please try again.");
      }
      if (await connection.getBlockHeight("confirmed") > freshLatest.lastValidBlockHeight) {
        throw new Error("The transaction expired while waiting for wallet approval. No payment was sent. Keep Phantom unlocked and try again.");
      }
      signature = getBase58Decoder().decode(signedTransaction.signature);
      // Save recovery details before broadcasting so a network timeout cannot cause a second payment.
      localStorage.setItem(recoveryKey, JSON.stringify({ id: purchase.id, signature, mint: mintAddress }));
      broadcastAttempted = true;
      transaction.advance("send");
      const sentSignature = await connection.sendRawTransaction(signedBytes, {
        skipPreflight: false,
        maxRetries: 5,
      });
      signature = sentSignature;
      transaction.advance("confirm", {signature: sentSignature, explorer: getExplorerUrl(`/tx/${sentSignature}`)});

      await waitForConfirmation(connection, sentSignature);

      // The blockchain transaction is now confirmed. Only now do we make
      // the marketplace state permanent in Django/PostgreSQL.
      transaction.advance("save");
      await confirmPurchase(purchase.id, {
        txSignature: sentSignature,
        mintAddress: mintPublicKey.toBase58(),
        cluster,
      });

      try { localStorage.removeItem(recoveryKey); } catch { /* The API has saved the purchase. */ }
      transaction.advance("success");
      onPurchased(sentSignature, wallet.account.address);

    } catch (error) {
      console.error(error);

      // Never release a reservation after a transaction signature exists.
      // The buyer may already have paid on-chain; the backend can be retried.
      if (purchaseId && !broadcastAttempted) {
        try { localStorage.removeItem(recoveryKey); } catch { /* No transaction was broadcast. */ }
        signature = undefined;
        await cancelPurchase(purchaseId).catch(() => undefined);
      }

      // Record an uncertain submission with the API too, preserving its reservation.
      if (purchaseId && signature && mintAddress && broadcastAttempted) {
        try {
          await confirmPurchase(purchaseId, { txSignature: signature, mintAddress, cluster });
          try { localStorage.removeItem(recoveryKey); } catch { /* The API has saved the purchase. */ }
          transaction.advance("success");
          onPurchased(signature, wallet.account.address);
          return;
        } catch { /* Keep recovery data and retry the original transaction, never send another payment. */ }
      }
      transaction.advance("error", {
        signature,
        explorer: signature ? getExplorerUrl(`/tx/${signature}`) : undefined,
        error: error instanceof Error ? error.message : "Unable to complete the purchase.",
      });
    }
  }

  return (
    <button
      onClick={handleBuy}
      disabled={transaction.active}
      aria-busy={transaction.active}
      className="rounded-lg border border-foreground/[0.075] bg-foreground/[0.035] px-3 py-2 text-xs font-medium text-foreground/60 transition hover:bg-foreground/[0.08] hover:text-foreground"
    >
      {transaction.active ? "Purchase in progress…" : "Buy rights →"}
    </button>
  );
}
