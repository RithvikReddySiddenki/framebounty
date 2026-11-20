const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, "../app/api.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function harness(fetch) {
  const sandbox = { exports: {}, process: { env: {} }, Error, fetch,
    AbortSignal: { timeout: milliseconds => ({ milliseconds }) } };
  vm.runInNewContext(compiled, sandbox);
  return sandbox.exports.request;
}

test("slow agent work fits the bounded chat budget while ordinary calls stay short", async () => {
  const request = harness(async (_url, options) => {
    // Simulate latency beyond the old deadline without a slow unit-test sleep.
    if (options.signal.milliseconds < 45000) throw Object.assign(new Error(), { name: "TimeoutError" });
    return { ok: true, json: async () => ({ reply: "Your post is ready" }) };
  });
  for (const route of ["/chat-sessions/session/messages", "/agent-sessions/session/messages"]) {
    assert.equal((await request(route, "token", { request_id: "same-request" })).reply, "Your post is ready");
  }
  await assert.rejects(request("/me/jobs", "token"), /took too long/);
});

test("AI timeouts preserve retry guidance and are not reported as network outages", async () => {
  const request = harness(async () => { throw Object.assign(new Error(), { name: "TimeoutError" }); });
  await assert.rejects(request("/chat-sessions/session/messages", "token", {}), /retry the same message/);
});

test("network failures and provider errors retain their distinct messages", async () => {
  const offline = harness(async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(offline("/me/jobs", "token"), /Cannot reach FrameBounty/);
  const provider = harness(async () => ({ ok: false, status: 503, json: async () => ({ detail: "AI provider temporarily unavailable" }) }));
  await assert.rejects(provider("/chat-sessions/session/messages", "token", {}), /AI provider temporarily unavailable/);
});

function walletHarness(provider) {
  const fetch = async (url) => ({
    ok: true,
    json: async () => url.endsWith("/auth/challenge")
      ? { nonce: "nonce", message: "Sign in to FrameBounty" }
      : { token: "session-token", expires_in_seconds: 60 },
  });
  const sandbox = { exports: {}, process: { env: {} }, Error, fetch, TextEncoder, Date,
    AbortSignal: { timeout: milliseconds => ({ milliseconds }) }, window: { ethereum: provider } };
  vm.runInNewContext(compiled, sandbox);
  return sandbox.exports.authenticate;
}

function fakeWallet({ known, approve }) {
  const calls = [];
  let chain = "0x1";
  return { calls, request: async ({ method, params }) => {
    calls.push(method);
    if (method === "eth_requestAccounts") return ["0x00000000000000000000000000000000000000aa"];
    if (method === "eth_chainId") return chain;
    if (method === "wallet_switchEthereumChain") {
      if (!approve) throw Object.assign(new Error("User rejected"), { code: 4001 });
      if (!known) throw Object.assign(new Error("Unrecognized chain"), { code: 4902 });
      chain = params[0].chainId; return null;
    }
    if (method === "wallet_addEthereumChain") {
      assert.equal(params[0].chainId, "0x4cef52");
      assert.equal(params[0].nativeCurrency.symbol, "USDC");
      known = true; chain = params[0].chainId; return null;
    }
    if (method === "personal_sign") return "0xsignature";
    throw new Error(`unexpected ${method}`);
  } };
}

test("sign-in adds Arc testnet to a wallet that does not know it, then continues", async () => {
  const wallet = fakeWallet({ known: false, approve: true });
  const session = await walletHarness(wallet)();
  assert.equal(session.token, "session-token");
  assert.ok(wallet.calls.includes("wallet_switchEthereumChain"));
  assert.ok(wallet.calls.includes("wallet_addEthereumChain"));
});

test("declining the network switch keeps the clear Arc testnet instruction", async () => {
  const wallet = fakeWallet({ known: true, approve: false });
  await assert.rejects(walletHarness(wallet)(), /Switch your wallet to Arc testnet/);
  assert.ok(!wallet.calls.includes("personal_sign"));
});

test("wallet events from sign-in itself never end a session; real changes do", () => {
  const sandbox = { exports: {}, process: { env: {} }, Error };
  vm.runInNewContext(compiled, sandbox);
  const ends = sandbox.exports.walletEventEndsSession;
  const wallet = "0xAbC0000000000000000000000000000000000001";
  // Before a session exists (mid sign-in), connect/switch events are ignored.
  for (const [event, payload] of [["accountsChanged", [wallet]], ["chainChanged", "0x1"], ["disconnect", undefined]])
    assert.equal(ends(event, payload, undefined), false);
  // Echoes of the signed-in account and Arc chain keep the session (case-insensitive).
  assert.equal(ends("accountsChanged", [wallet.toLowerCase()], wallet), false);
  assert.equal(ends("chainChanged", "0x4cef52", wallet), false);
  // Real changes end it; payload-less events fail closed.
  assert.equal(ends("accountsChanged", ["0x0000000000000000000000000000000000000002"], wallet), true);
  assert.equal(ends("accountsChanged", [], wallet), true);
  assert.equal(ends("accountsChanged", undefined, wallet), true);
  assert.equal(ends("chainChanged", "0x1", wallet), true);
  assert.equal(ends("disconnect", undefined, wallet), true);
});
