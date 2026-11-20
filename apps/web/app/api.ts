"use client";

export const apiBase =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type WalletTransaction = { from: string; to: string; data: string; value: string; chainId: string };
let embeddedSender: ((transaction: WalletTransaction, intentId?: string) => Promise<string>) | undefined;
let embeddedDraftRemover: ((jobId: string) => Promise<unknown>) | undefined;
export function setEmbeddedDraftRemover(remove: (jobId: string) => Promise<unknown>) { embeddedDraftRemover = remove; }
export function removeDraft(jobId: string, token: string) {
  return embeddedDraftRemover ? embeddedDraftRemover(jobId) : request(`/jobs/${jobId}/remove`, token, {});
}
export function setEmbeddedWalletSender(sender?: (transaction: WalletTransaction, intentId?: string) => Promise<string>) {
  embeddedSender = sender;
  if (!sender) embeddedDraftRemover = undefined;
}
let activeChain = Number(process.env.NEXT_PUBLIC_ARC_CHAIN_ID || "5042002");
export function configureArcNetwork(chainId: number) {
  if (![5042, 5042002].includes(chainId)) throw new Error("Unsupported FrameBounty network.");
  activeChain = chainId;
}
export const moneyUnit = (fixture = false) => fixture ? "simulated USDC" : activeChain === 5042 ? "USDC" : "test USDC";
export const networkName = () => activeChain === 5042 ? "Arc mainnet" : "Arc testnet";
export const explorerUrl = () => activeChain === 5042 ? "https://explorer.arc.io" : "https://explorer.testnet.arc.io";
const chainHex = () => "0x" + activeChain.toString(16);

export function notifySessionExpired(token: string) {
  window.dispatchEvent(
    new CustomEvent("framebounty:session-expired", { detail: { token } }),
  );
}

export async function request<T>(
  path: string,
  token?: string,
  body?: unknown,
): Promise<T> {
  let response: Response;
  // Contributor chat may make two bounded 45-second model calls (intake and
  // ranking). Do not abandon a healthy request at the normal API's 15s limit.
  const agentMessage = body !== undefined && /^\/(chat-sessions|agent-sessions)\/[^/]+\/messages$/.test(path);
  const circleRequest = path.startsWith("/auth/circle/") || path.startsWith("/circle/transactions");
  try {
    response = await fetch(apiBase + path, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(agentMessage || circleRequest ? 120000 : 15000),
    });
  } catch (error) {
    if (error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name)) {
      throw new Error(circleRequest ? "Circle is taking longer than expected. Retry the same action to check its existing authorization." : agentMessage
        ? "The AI is taking longer than expected. Your message is kept; retry the same message to check for its result."
        : "FrameBounty took too long to respond. Please retry.");
    }
    throw new Error(
      "Cannot reach FrameBounty. Check that the API is running and try again.",
    );
  }
  if (!response.ok) {
    if (response.status === 401 && token) notifySessionExpired(token);
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
  on?: (event: string, listener: (payload?: unknown) => void) => void;
  removeListener?: (event: string, listener: (payload?: unknown) => void) => void;
};

export type WalletEvent = "accountsChanged" | "chainChanged" | "disconnect";
const WALLET_EVENTS: WalletEvent[] = ["accountsChanged", "chainChanged", "disconnect"];

/** Decide whether a wallet event must end the signed-in session.
 *
 * Sign-in itself calls eth_requestAccounts and switches to Arc, which makes
 * MetaMask emit accountsChanged/chainChanged, sometimes after login returns.
 * Treating those as "the user changed wallets" signed people out the instant
 * they signed in. So: with no session, events are ignored (the server already
 * verifies the signature matches the wallet). With a session, only a real
 * change ends it: another account, a non-Arc chain, a disconnect, or an event
 * with no usable payload (fail closed). */
export function walletEventEndsSession(event: WalletEvent, payload: unknown, wallet?: string): boolean {
  if (!wallet) return false;
  if (event === "accountsChanged")
    return !(Array.isArray(payload) && typeof payload[0] === "string" && payload[0].toLowerCase() === wallet.toLowerCase());
  if (event === "chainChanged") return payload !== chainHex();
  return true;
}

export function watchWalletChange(
  onEvent: (event: WalletEvent, payload: unknown) => void,
  sessionExpired: (token: string) => void,
): () => void {
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  // Keep exact references so removeListener detaches the same functions.
  const listeners = WALLET_EVENTS.map(event => [event, (payload?: unknown) => onEvent(event, payload)] as const);
  listeners.forEach(([event, listener]) => provider?.on?.(event, listener));
  const expired = (event: Event) => {
    const token = (event as CustomEvent<{ token: string }>).detail?.token;
    if (token) sessionExpired(token);
  };
  window.addEventListener("framebounty:session-expired", expired);
  return () => {
    listeners.forEach(([event, listener]) => provider?.removeListener?.(event, listener));
    window.removeEventListener("framebounty:session-expired", expired);
  };
}

const arcNetwork = () => ({
  chainId: chainHex(),
  chainName: activeChain === 5042 ? "Arc" : "Arc Testnet",
  // Arc's native gas balance is USDC with 18 decimals (the ERC-20 view uses 6).
  nativeCurrency: { name: "USDC", symbol: "USDC", decimals: 18 },
  rpcUrls: [activeChain === 5042 ? "https://rpc.mainnet.arc.io" : "https://rpc.testnet.arc.io"],
  blockExplorerUrls: [activeChain === 5042 ? "https://explorer.arc.io" : "https://explorer.testnet.arc.io"],
});

/** Ask the wallet to switch to Arc testnet, adding the network first if the
 * wallet doesn't know it (EIP-3085 / EIP-3326). Returns the resulting chain. */
async function ensureArcTestnet(provider: Provider): Promise<unknown> {
  const ARC_TESTNET = arcNetwork();
  const chain = await provider.request({ method: "eth_chainId" });
  if (chain === ARC_TESTNET.chainId) return chain;
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: ARC_TESTNET.chainId }],
    });
  } catch (error) {
    const code = (error as { code?: number })?.code;
    // 4902: unrecognized chain. Some wallets report it as -32603 with nested data.
    const nested = (error as { data?: { originalError?: { code?: number } } })?.data?.originalError?.code;
    if (code !== 4902 && nested !== 4902) throw error;
    await provider.request({ method: "wallet_addEthereumChain", params: [ARC_TESTNET] });
  }
  return provider.request({ method: "eth_chainId" });
}

/** Translate EIP-1193 wallet error codes into actionable sign-in guidance.
 * -32002 is the common trap: an earlier popup is still open (often hidden behind
 * the browser window), so every later click fails instantly without a prompt. */
export function walletErrorMessage(error: unknown): string {
  const code = (error as { code?: number })?.code;
  if (code === 4001)
    return "Signature request was rejected in your wallet. Click sign in again and approve the message.";
  if (code === -32002)
    return "Your wallet already has a pending request. Click the MetaMask extension icon to finish or dismiss it, then try again.";
  if (code === 4100)
    return "Your wallet hasn't authorized this site. Unlock your wallet and connect this account, then retry.";
  const message = (error as { message?: string })?.message;
  return message ? `Wallet error: ${message}` : "Wallet sign-in failed. Check your wallet extension and retry.";
}

export async function authenticate(): Promise<{
  wallet: string;
  token: string;
  expiresAt: number;
}> {
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  if (!provider)
    throw new Error(
      "Install or open an Ethereum-compatible browser wallet to sign in.",
    );
  configureArcNetwork((await request<{ chain_id: number }>("/auth/config")).chain_id);
  let accounts: string[];
  try {
    accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
  } catch (error) {
    throw new Error(walletErrorMessage(error));
  }
  const wallet = accounts[0];
  if (!wallet) throw new Error("No wallet account was selected.");
  let chain: unknown;
  try {
    chain = await ensureArcTestnet(provider);
  } catch {
    chain = await provider.request({ method: "eth_chainId" });
  }
  if (chain !== chainHex())
    throw new Error(
      activeChain === 5042 ? "Switch your wallet to Arc mainnet (chain 5042), then try again." : "Switch your wallet to Arc testnet (chain 5042002), then try again.",
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
  let signature: unknown;
  try {
    signature = await provider.request({
      method: "personal_sign",
      params: [hex, wallet],
    });
  } catch (error) {
    throw new Error(walletErrorMessage(error));
  }
  const result = await request<{ token: string; expires_in_seconds: number }>(
    "/auth/login",
    undefined,
    {
      nonce: challenge.nonce,
      signature,
    },
  );
  // Session stays in memory; reloading requires another signature. Never persist a signing key.
  return {
    wallet,
    token: result.token,
    expiresAt: Date.now() + result.expires_in_seconds * 1000,
  };
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
}, intentId?: string): Promise<string> {
  if (embeddedSender) return embeddedSender(transaction, intentId);
  const provider = (window as Window & { ethereum?: Provider }).ethereum;
  if (!provider) throw new Error("Open your connected browser wallet.");
  const accounts = (await provider.request({
    method: "eth_accounts",
  })) as string[];
  const chain = await provider.request({ method: "eth_chainId" });
  if (chain !== chainHex() || transaction.chainId !== chain)
    throw new Error(
      "Switch to " + networkName() + " before authorizing this transaction.",
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
