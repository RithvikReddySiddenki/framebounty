"use client";

export const apiBase =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function request<T>(
  path: string,
  token?: string,
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiBase + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error(
      "Cannot reach FrameBounty. Check that the API is running and try again.",
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}). Please check your input and retry.`,
    );
  }
  return response.json() as Promise<T>;
}

type Provider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, listener: () => void) => void;
  removeListener?: (event: string, listener: () => void) => void;
};

export function watchWalletChange(disconnect: () => void): () => void {
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  provider?.on?.("accountsChanged", disconnect);
  provider?.on?.("chainChanged", disconnect);
  return () => {
    provider?.removeListener?.("accountsChanged", disconnect);
    provider?.removeListener?.("chainChanged", disconnect);
  };
}

export async function authenticate(): Promise<{
  wallet: string;
  token: string;
}> {
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  if (!provider)
    throw new Error(
      "Install or open an Ethereum-compatible browser wallet to sign in.",
    );
  const accounts = (await provider.request({
    method: "eth_requestAccounts",
  })) as string[];
  const wallet = accounts[0];
  if (!wallet) throw new Error("No wallet account was selected.");
  const chain = await provider.request({ method: "eth_chainId" });
  if (chain !== "0x4cef52")
    throw new Error(
      "Switch your wallet to Arc testnet (chain 5042002), then try again.",
    );
  const challenge = await request<{ nonce: string; message: string }>(
    "/auth/challenge",
    undefined,
    { wallet },
  );
  const hex =
    "0x" +
    Array.from(new TextEncoder().encode(challenge.message), (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
  const signature = await provider.request({
    method: "personal_sign",
    params: [hex, wallet],
  });
  const result = await request<{ token: string }>("/auth/login", undefined, {
    nonce: challenge.nonce,
    signature,
  });
  // Session stays in memory; reloading requires another signature. Never persist a signing key.
  return { wallet, token: result.token };
}

export function usdc(atomic: string): string {
  const amount = BigInt(atomic);
  return `${amount / 1000000n}.${(amount % 1000000n).toString().padStart(6, "0").replace(/0+$/, "") || "0"}`;
}

export async function sendFundingTransaction(transaction: {
  from: string;
  to: string;
  data: string;
  value: string;
  chainId: string;
}): Promise<string> {
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  if (!provider) throw new Error("Open your connected browser wallet.");
  const accounts = (await provider.request({
    method: "eth_accounts",
  })) as string[];
  const chain = await provider.request({ method: "eth_chainId" });
  if (chain !== "0x4cef52" || transaction.chainId !== chain)
    throw new Error(
      "Switch to Arc testnet before authorizing this transaction.",
    );
  if (accounts[0]?.toLowerCase() !== transaction.from.toLowerCase())
    throw new Error("Reconnect the wallet that owns this action.");
  const hash = await provider.request({
    method: "eth_sendTransaction",
    params: [transaction],
  });
  if (typeof hash !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(hash))
    throw new Error(
      "Wallet returned no transaction hash. Check wallet activity before retrying.",
    );
  return hash;
}

export const sendWalletTransaction = sendFundingTransaction;
