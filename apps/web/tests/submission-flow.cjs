const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
function compile(file) { return ts.transpileModule(fs.readFileSync(path.join(__dirname, "../app", file), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText; }
const coordinator = { exports: {} }; vm.runInNewContext(compile("publishing.ts"), coordinator);

test("one submit action authorizes once and recovers a lost response without signing again", async () => {
  const stored = new Map(); let sends = 0, loseResponse = true;
  const api = {
    request: async (route, token, body) => {
      assert.equal(route, "/reservations/reservation-a/chain");
      assert.equal(body.purpose, "submit"); assert.equal(body.confirmed, true);
      if (body.tx_hash) {
        assert.equal(body.tx_hash, "signed-hash");
        if (loseResponse) { loseResponse = false; throw new Error("Lost response"); }
        return { confirmed: true, state: "confirmed", intent_id: "exact-intent" };
      }
      return { confirmed: false, state: "intent", intent_id: "exact-intent", transaction: { data: "exact-data" } };
    },
    sendWalletTransaction: async (transaction, id) => {
      sends++; assert.equal(transaction.data, "exact-data"); assert.equal(id, "exact-intent"); return "signed-hash";
    },
  };
  const context = { exports: {}, require: name => name === "./api" ? api : coordinator.exports,
    sessionStorage: { getItem: k => stored.get(k), setItem: (k,v) => stored.set(k,v), removeItem: k => stored.delete(k) },
    window: { setTimeout: resolve => resolve() }, Error };
  vm.runInNewContext(compile("submit-flow.ts"), context);
  const controller = new AbortController();
  await assert.rejects(context.exports.confirmUploadedSubmission("token", "reservation-a", controller.signal), /Lost response/);
  assert.equal(sends, 1); assert.equal(stored.size, 1);
  await context.exports.confirmUploadedSubmission("token", "reservation-a", controller.signal);
  assert.equal(sends, 1); assert.equal(stored.size, 0);
});
