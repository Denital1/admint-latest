export type Surface = {
  id: number;
  location?: string;
  photo?: string|null;
  title: string;
  owner: string;
  type: "Physical" | "Digital";
  duration: string;
  price: string;
  priceSol: number;
  emoji: string;
  tagline: string;
  accent: string;
  ownerAccountId?: number;
  sellerAddress?: string;
  status?: "available" | "reserved" | "sold";
  buyerAddress?: string;
  txSignature?: string;
  mintAddress?: string;
};

export type Purchase = {
  id: number;
  listing: number;
  listing_title: string;
  buyer_wallet: string;
  seller_wallet: string;
  price_sol: string;
  status: "pending" | "confirmed" | "failed" | "cancelled";
  tx_signature: string | null;
  mint_address: string;
  verification_message: string;
  created_at: string;
  confirmed_at: string | null;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "/api"
).replace(/\/$/, "");

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let csrfToken = "";
  if (init?.method && init.method !== "GET") {
    const session = await fetch("/api/auth/session/", { credentials: "include", cache: "no-store" });
    if (!session.ok) throw new Error("Unable to initialize your session.");
    csrfToken = (await session.json()).csrfToken;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      "X-CSRFToken": csrfToken,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String(body.detail)
        : "AdMint API request failed.";
    throw new Error(detail);
  }

  return body as T;
}

export async function getListings(): Promise<Surface[]> {
  const data = await apiRequest<
    Array<{
      id: number;
      location?: string;
      photo?: string|null;
      title: string;
      owner: string;
      surfaceType: "Physical" | "Digital";
      duration: string;
      price: string;
      price_sol: string;
      emoji: string;
      tagline: string;
      accent: string;
      ownerAccountId?: number;
    sellerAddress: string;
      status: "available" | "reserved" | "sold";
      buyerAddress: string;
      txSignature: string;
      mintAddress: string;
    }>
  >("/listings/");

  return data.map((listing) => ({
    id: listing.id,
    location: listing.location,
    photo: listing.photo,
    title: listing.title,
    owner: listing.owner,
    type: listing.surfaceType,
    duration: listing.duration,
    price: listing.price,
    priceSol: Number(listing.price_sol),
    emoji: listing.emoji,
    tagline: listing.tagline,
    accent: listing.accent,
    ownerAccountId: listing.ownerAccountId,
    sellerAddress: listing.sellerAddress || undefined,
    status: listing.status,
    buyerAddress: listing.buyerAddress || undefined,
    txSignature: listing.txSignature || undefined,
    mintAddress: listing.mintAddress || undefined,
  }));
}

export async function createListing(input: {
  title: string;
  owner: string;
  surfaceType: "Physical" | "Digital";
  duration: string;
  priceSol: number;
  emoji: string;
  tagline: string;
  accent: string;
  sellerWallet: string;
  photoFile?: File;
}): Promise<Surface> {
  const payload = {
    title: input.title, owner: input.owner, surfaceType: input.surfaceType,
    duration: input.duration, priceSol: input.priceSol, emoji: input.emoji,
    tagline: input.tagline, accent: input.accent, seller_wallet: input.sellerWallet,
  };
  const form = new FormData();
  for (const [key, value] of Object.entries(payload)) form.append(key, String(value));
  if (input.photoFile) form.append("photo", input.photoFile);
  const listing = await apiRequest<{
    id: number;
    title: string;
    owner: string;
    surfaceType: "Physical" | "Digital";
    duration: string;
    price: string;
    price_sol: string;
    emoji: string;
    tagline: string;
    accent: string;
    ownerAccountId?: number;
    sellerAddress: string;
    photo?: string | null;
    status: "available" | "reserved" | "sold";
    buyerAddress: string;
    txSignature: string;
    mintAddress: string;
  }>("/listings/", {
    method: "POST",
    body: form,
  });

  return {
    id: listing.id,
    photo: listing.photo,
    title: listing.title,
    owner: listing.owner,
    type: listing.surfaceType,
    duration: listing.duration,
    price: listing.price,
    priceSol: Number(listing.price_sol),
    emoji: listing.emoji,
    tagline: listing.tagline,
    accent: listing.accent,
    ownerAccountId: listing.ownerAccountId,
    sellerAddress: listing.sellerAddress || undefined,
    status: listing.status,
    buyerAddress: listing.buyerAddress || undefined,
    txSignature: listing.txSignature || undefined,
    mintAddress: listing.mintAddress || undefined,
  };
}

export async function preparePurchase(
  listingId: number,
  buyerWallet: string,
  cluster = "devnet",
): Promise<Purchase> {
  return apiRequest<Purchase>("/purchases/prepare/", {
    method: "POST",
    body: JSON.stringify({
      listing_id: listingId,
      buyer_wallet: buyerWallet,
      cluster,
    }),
  });
}

export async function confirmPurchase(
  purchaseId: number,
  input: { txSignature: string; mintAddress: string; cluster: string },
): Promise<Purchase> {
  return apiRequest<Purchase>(`/purchases/${purchaseId}/confirm/`, {
    method: "POST",
    body: JSON.stringify({
      tx_signature: input.txSignature,
      mint_address: input.mintAddress,
      cluster: input.cluster,
    }),
  });
}

export async function cancelPurchase(purchaseId: number): Promise<Purchase> {
  return apiRequest<Purchase>(`/purchases/${purchaseId}/cancel/`, {
    method: "POST",
  });
}

export async function getMyPurchases(wallet: string): Promise<Purchase[]> {
  return apiRequest<Purchase[]>(
    `/purchases/?wallet=${encodeURIComponent(wallet)}`,
  );
}

export async function getMyAdRights(wallet: string) {
  return apiRequest<
    Array<{
      id: number;
      listing: number;
      listing_title: string;
      owner_wallet: string;
      mint_address: string;
      transaction_signature: string;
      acquired_at: string;
    }>
  >(`/ad-rights/?wallet=${encodeURIComponent(wallet)}`);
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}
