const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Compile the exact production coordinator in memory. Wallet and RPC are
// external boundaries; the actual receipt-driven progression is under test.
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, "../app/publishing.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(compiled, sandbox);
const { publishApprovedPlan } = sandbox.exports;
const intent = id => ({ funded: false, state: "intent", intent_id: id, transaction: { from: "buyer", to: id, data: "0x", value: "0x0", chainId: "0x4cef52" } });

function harness() {
  let pending;
  const sends = [], saved = [], steps = [];
  const controller = new AbortController();
  return { sends, saved, steps, controller, pending: () => pending,
    options: {
      signal: controller.signal, read: () => pending,
      save: next => { pending = next; saved.push(next); },
      send: async transaction => { sends.push(transaction.to); return "hash-" + transaction.to; },
      changed: step => steps.push(step), wait: async () => {},
    },
  };
}

test("one approved action advances three exact instructions through receipts", async () => {
  const h = harness(); let calls = 0;
  const responses = [intent("create"), { funded: false, state: "broadcast", intent_id: "create" }, intent("allowance"), intent("deposit"), { funded: true, state: "open" }];
  await publishApprovedPlan({ ...h.options, load: async pending => {
    if (calls > 0) assert.equal(h.pending(), pending, "persist hash before API call");
    return responses[calls++];
  } });
  assert.deepEqual(h.sends, ["create", "allowance", "deposit"]);
  assert.equal(h.pending(), undefined);
});

test("lost API response retains hash; restart does not send again", async () => {
  const h = harness(); let calls = 0;
  await assert.rejects(publishApprovedPlan({ ...h.options, load: async () => {
    if (calls++ === 0) return intent("deposit");
    throw new Error("API connection lost");
  } }), /connection lost/);
  assert.equal(h.pending().tx_hash, "hash-deposit");
  await publishApprovedPlan({ ...h.options, load: async pending => {
    assert.equal(pending.tx_hash, "hash-deposit"); return { funded: true, state: "open" };
  } });
  assert.deepEqual(h.sends, ["deposit"]);
});

test("declining a wallet request stops subsequent prompts", async () => {
  const h = harness(); let calls = 0;
  await assert.rejects(publishApprovedPlan({ ...h.options,
    load: async () => { calls++; return intent("create"); }, send: async () => { throw new Error("User declined"); },
  }), /declined/);
  assert.equal(calls, 1); assert.equal(h.pending(), undefined);
});

test("navigation while wallet is open saves returned hash and stops later prompts", async () => {
  const h = harness(); let calls = 0;
  await assert.rejects(publishApprovedPlan({ ...h.options, load: async () => { calls++; return intent("create"); },
    send: async () => { h.controller.abort(); return "hash-after-navigation"; },
  }), /stopped/);
  assert.equal(h.pending().tx_hash, "hash-after-navigation"); assert.equal(calls, 1);
});

test("pending timeout preserves recovery state without resending", async () => {
  const h = harness(); h.options.save({ intent_id: "deposit", tx_hash: "existing" });
  await assert.rejects(publishApprovedPlan({ ...h.options, maxChecks: 2,
    load: async () => ({ funded: false, state: "broadcast", intent_id: "deposit" }),
  }), /Still waiting/);
  assert.equal(h.pending().tx_hash, "existing"); assert.equal(h.sends.length, 0);
});

test("reverted receipt is never treated as funded or sent again", async () => {
  const h = harness(); h.options.save({ intent_id: "deposit", tx_hash: "reverted" });
  await assert.rejects(publishApprovedPlan({ ...h.options,
    load: async () => ({ funded: false, state: "reverted", intent_id: "deposit", last_error: "Receipt reverted" }),
  }), /reverted/);
  assert.equal(h.pending().tx_hash, "reverted"); assert.equal(h.sends.length, 0);
});
