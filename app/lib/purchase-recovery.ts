export type PendingPurchase = { id: number; signature: string; mint: string };

export function decodePendingPurchase(raw: string | null): PendingPurchase | null {
  try {
    const data = JSON.parse(raw || "null");
    return data && Number.isSafeInteger(data.id) && data.id > 0 &&
      typeof data.signature === "string" && /^[1-9A-HJ-NP-Za-km-z]{64,88}$/.test(data.signature) &&
      typeof data.mint === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(data.mint)
      ? { id: data.id, signature: data.signature, mint: data.mint } : null;
  } catch { return null; }
}

export function purchaseLamports(price: string): number {
  if (!/^\d+(\.\d{1,9})?$/.test(price)) throw new Error("Invalid purchase price.");
  const [whole, fractional = ""] = price.split(".");
  const value = BigInt(whole) * 1_000_000_000n + BigInt(fractional.padEnd(9, "0"));
  if (value <= 0n || value > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("This price cannot be represented safely in lamports.");
  }
  return Number(value);
}
