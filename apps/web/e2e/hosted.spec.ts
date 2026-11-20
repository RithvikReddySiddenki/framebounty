/** Explicit hosted demo gate. Real deployed UI/API/storage/worker; synthetic
 * browser camera and ephemeral wallet signatures. Never authorizes chain funds. */
import { test, expect, type Page } from "@playwright/test";
import { Wallet, getBytes } from "ethers";

const web = process.env.HOSTED_SMOKE_URL;
const api = process.env.HOSTED_API_URL;
test.skip(!web || !api, "Explicit hosted fixture-only smoke; creates labeled synthetic test posts");
test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] } });
test.setTimeout(180000);

async function login(page: Page) {
  const wallet = Wallet.createRandom();
  await page.exposeFunction("hostedWallet", async ({ method, params }: { method: string; params?: string[] }) => {
    if (method === "eth_requestAccounts" || method === "eth_accounts") return [wallet.address];
    if (method === "eth_chainId") return "0x4cef52";
    if (method === "personal_sign") return wallet.signMessage(getBytes(params![0]));
    throw new Error("Unexpected wallet action; hosted smoke never transacts: " + method);
  });
  await page.addInitScript(() => Object.defineProperty(window, "ethereum", { value: {
    on() {}, removeListener() {}, request: (args: unknown) => (window as unknown as {
      hostedWallet: (args: unknown) => Promise<unknown>;
    }).hostedWallet(args),
  } }));
  const overview = page.waitForRequest(r => r.url() === api + "/me/overview");
  await page.goto(web!);
  await page.getByRole("button", { name: /Connect wallet/ }).click();
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible({ timeout: 30000 });
  const authorization = (await overview).headers()["authorization"];
  const headers = { Authorization: authorization };
  const status = await page.request.get(api + "/me/status", { headers });
  expect(status.ok()).toBeTruthy();
  const state = await status.json();
  // Abort before creating jobs if pointed at a live funding environment.
  expect(state.mode).toBe("fixture");
  expect(state.payments_enabled).toBe(false);
  return headers;
}

for (const format of ["PNG", "JPEG", "video"] as const) {
  test(`hosted ${format}: submit, deployed verification, protected preview, release and export`, async ({ browser }, info) => {
    expect(new URL(web!).protocol).toBe("https:");
    expect(new URL(api!).protocol).toBe("https:");
    const buyerContext = await browser.newContext();
    const actorContext = await browser.newContext({ permissions: ["camera"] });
    const buyer = await buyerContext.newPage(), actor = await actorContext.newPage();
    try {
      const buyerHeaders = await login(buyer);
      const actorHeaders = await login(actor);
      const image = format !== "video";
      const title = `Hosted synthetic ${format} ${Date.now()}`;
      const created = await buyer.request.post(api + "/jobs", { headers: buyerHeaders, data: {
        title, media_type: image ? "image" : "video", verification_policy: "ai", version: 1,
        total: 1, budget_atomic: 1000000, reward_atomic: 1000000, min_seconds: 10, max_seconds: 30,
        review_hours: 72, expected_minutes: 15, requirements: [],
        rights_declaration: "Synthetic deployment test pattern only; no real task, person or authenticity claim.",
      } });
      expect(created.ok()).toBeTruthy();
      const job = await created.json();
      const published = await buyer.request.post(`${api}/jobs/${job.id}/fixture-publish`, { headers: buyerHeaders,
        data: { plan_hash: job.plan_hash, confirmed: true } });
      expect(published.ok()).toBeTruthy();
      await actor.getByRole("button", { name: "Contributor workspace" }).click();
      await actor.getByLabel("Message your work agent").fill("I have a phone, a towel and a dark table. I have 20 minutes.");
      await actor.getByRole("button", { name: "Send", exact: true }).click();
      const match = actor.locator(".agent-task").filter({ hasText: title });
      await expect(match).toBeVisible({ timeout: 30000 });
      await match.getByRole("button", { name: /Review reservation for/ }).click();
      await match.getByRole("button", { name: /Accept fixed terms for/ }).click();
      if (image) {
        const mime = format === "PNG" ? "image/png" : "image/jpeg";
        const encoded = await actor.evaluate(type => {
          const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 240;
          const c = canvas.getContext("2d")!; c.fillStyle = "green"; c.fillRect(0, 0, 320, 240);
          return canvas.toDataURL(type).split(",")[1];
        }, mime);
        await actor.getByLabel("Choose an image").setInputFiles({ name: "synthetic." + (format === "PNG" ? "png" : "jpg"),
          mimeType: mime, buffer: Buffer.from(encoded, "base64") });
      } else {
        await expect(actor.locator('input[type="file"]')).toHaveCount(0);
        await actor.getByRole("button", { name: "Open camera", exact: true }).click();
        await expect(actor.getByLabel("Live camera preview")).toBeVisible();
        await actor.getByRole("button", { name: "Start recording", exact: true }).click();
        await actor.waitForTimeout(12000);
        await actor.getByRole("button", { name: "Stop recording", exact: true }).click();
        await expect(actor.getByLabel("Recorded video review")).toBeVisible();
      }
      const uploadResponse = actor.waitForResponse(r => r.request().method() === "POST" && r.url().includes("/media?"));
      await actor.getByRole("button", { name: image ? "Upload image" : "Submit recording", exact: true }).click();
      const response = await uploadResponse;
      expect(response.ok()).toBeTruthy();
      if (!image) expect(response.request().headers()["x-capture-token"]).toBeTruthy();
      const submitted = await response.json();
      const itemURL = `${api}/submissions/${submitted.id}`;
      await expect.poll(async () => (await (await actor.request.get(itemURL, { headers: actorHeaders })).json()).state,
        { timeout: 90000, intervals: [1000, 2000, 3000] }).toBe("verified");
      const verified = await (await actor.request.get(itemURL, { headers: actorHeaders })).json();
      expect(verified.findings.decoded).toBe(true);
      expect(verified.payment_confirmed).toBe(false);
      expect((await buyer.request.get(itemURL + "/media")).status()).toBe(401);
      const preview = await buyer.request.get(itemURL + "/preview", { headers: buyerHeaders });
      expect(preview.status()).toBe(200);
      expect(preview.headers()["content-type"]).toContain("image/jpeg");
      if (!image) expect((await buyer.request.get(itemURL + "/media", { headers: buyerHeaders })).status()).toBe(403);
      expect((await (await buyer.request.get(`${api}/jobs/${job.id}/export`, { headers: buyerHeaders })).json()).items).toEqual([]);
      await buyer.getByRole("button", { name: "Collections & review", exact: true }).click();
      await buyer.locator(".post-card").filter({ hasText: title }).click();
      await expect(buyer.getByRole("button", { name: "Release simulated funds", exact: true })).toBeEnabled();
      await buyer.getByRole("button", { name: "Release simulated funds", exact: true }).click();
      await expect.poll(async () => (await (await actor.request.get(itemURL, { headers: actorHeaders })).json()).state).toBe("fixture_accepted");
      const original = await buyer.request.get(itemURL + "/media", { headers: buyerHeaders });
      expect(original.ok()).toBeTruthy();
      if (image) expect((await original.body()).equals(await preview.body())).toBe(false);
      const archive = await buyer.request.get(`${api}/jobs/${job.id}/dataset.zip`, { headers: buyerHeaders });
      expect(archive.ok()).toBeTruthy();
      expect((await archive.body()).subarray(0, 2).toString()).toBe("PK");
      await buyer.screenshot({ path: info.outputPath("paid-submission.png"), fullPage: true });
      await info.attach("public-result", { body: JSON.stringify({ format, job: job.id, submission: submitted.id,
        decoded: true, fixture: true, real_payment: false, export_bytes: (await archive.body()).length }), contentType: "application/json" });
    } finally { await buyerContext.close(); await actorContext.close(); }
  });
}
