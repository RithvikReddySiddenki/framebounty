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
