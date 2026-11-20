import { test, expect, Page } from "@playwright/test";
import { Wallet, getBytes } from "ethers";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

test("buyer retries the same message and waits beyond the old 15-second cutoff", async ({ page }) => {
  await connect(page);
  const bodies: { message: string; request_id: string }[] = [];
  await page.route("**/chat-sessions/*/messages", async route => {
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "AI provider temporarily unavailable" }) });
      return;
    }
    // Reproduce real model latency against the actual fixture API, beyond the
    // old browser timeout. No live model, wallet payment or fake post response.
    await new Promise(resolve => setTimeout(resolve, 16000));
    await route.continue();
  });
  const message = "I want 20 images of a cat climbing a tree, spend only 20 USDC.";
  await page.getByLabel("Describe your task").fill(message);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".post-composer [role=alert]")).toHaveText("AI provider temporarily unavailable");
  await expect(page.getByLabel("Describe your task")).toHaveValue(message);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/Preparing your post/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Generated post preview" })).toBeVisible({ timeout: 25000 });
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toEqual(bodies[0]);
  await expect(page.locator(".post-composer [role=alert]")).toHaveCount(0);
});

test("draft funding and review panels have distinct identities across post selection", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING !== "true", "Separate funding-UI regression gate; no wallet transactions");
  const errors: string[] = [];
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  const authenticated = page.waitForRequest(req => req.url().endsWith("/me/overview"));
  await connect(page);
  const authorization = (await authenticated).headers()["authorization"];
  for (const title of ["First draft image post", "Second draft image post"]) {
    const response = await page.request.post("http://127.0.0.1:8002/jobs", {
      headers: { Authorization: authorization }, data: {
        media_type: "image", version: 1, title, total: 1, budget_atomic: 1000000,
        reward_atomic: 1000000, min_seconds: 10, max_seconds: 10, review_hours: 72,
        rights_declaration: "Synthetic UI test data only; no actual collection.", requirements: [],
      },
    });
    expect(response.ok()).toBe(true);
  }
  await page.getByRole("button", { name: "Collections & review", exact: true }).click();
  await page.locator(".post-card").filter({ hasText: "First draft image post" }).click();
  await page.getByText("Recover a wallet transaction", { exact: true }).click();
  const recovery = page.getByLabel("Existing transaction hash");
  await recovery.fill("0x1234");
  await expect(page.getByRole("button", { name: "Refresh queue & coverage" })).toBeVisible();
  await page.locator(".post-card").filter({ hasText: "Second draft image post" }).click();
  await page.getByText("Recover a wallet transaction", { exact: true }).click();
  await expect(recovery).toHaveValue("");
  await expect(page.locator(".post-detail").getByRole("heading", { name: "Second draft image post", exact: true })).toBeVisible();
  expect(errors.filter(error => /same key|unique.*key/i.test(error))).toEqual([]);
});

test("image request becomes a labeled post, automatic verification and final funds release", async ({ browser }) => {
  const buyerContext = await browser.newContext();
  const actorContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const buyer = await buyerContext.newPage();
  const actor = await actorContext.newPage();
  await connect(buyer);
  await expect(buyer.getByText("Submission updates", { exact: true })).toBeVisible();
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("I want images of a cat climbing a tree");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  await expect(buyer.getByText(/How many would you like/)).toBeVisible();
  await expect(buyer.getByRole("region", { name: "Generated post preview" })).toHaveCount(0);
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("20");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  await expect(buyer.getByText(/maximum reward budget/)).toBeVisible();
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("20 USDC");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  const preview = buyer.getByRole("region", { name: "Generated post preview" });
  await expect(preview.getByText("Image post", { exact: true })).toBeVisible();
  await buyer.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "buyer-chat-preview.png"), fullPage: true });
  await buyer.getByText("More options", { exact: true }).click();
  await buyer.getByRole("button", { name: "Save draft instead" }).click();
  await buyer.getByRole("button", { name: "View my posts & status" }).click();
  const card = buyer.locator(".post-card").filter({ hasText: /cat climbing a tree/i });
  await expect(card).toContainText("Draft");
  await buyer.getByRole("button", { name: "Overview", exact: true }).click();
  await buyer.getByRole("button", { name: "Publish simulated post" }).click();
  await buyer.getByRole("button", { name: "View my posts & status" }).click();
  await expect(card).toContainText("Open for contributors");
  await card.click();
  await connect(actor);
  await actor.getByRole("button", { name: "Contributor workspace" }).click();
  await actor.getByLabel("Message your work agent").fill("I have a cat. What kinds of tasks are available for me.");
  await actor.getByRole("button", { name: "Send", exact: true }).click();
  // Tasks show right away; the agent never asks about time.
  await expect(actor.getByText(/Matching on: cat\./)).toBeVisible();
  await expect(actor.getByText(/How much time do you have/)).toHaveCount(0);
  await expect(actor.getByLabel("Equipment (comma-separated)")).toHaveCount(0);
  await actor.getByLabel("Message your work agent").fill("I have a phone to record and take pictures");
  await actor.getByRole("button", { name: "Send", exact: true }).click();
  await expect(actor.getByText(/Matching on: cat, phone/)).toBeVisible();
  const match = actor.locator(".agent-task").filter({ hasText: /cat climbing a tree/i });
  await expect(match.getByText("Image post", { exact: true })).toBeVisible();
  await actor.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "work-chat-mobile.png"), fullPage: true });
  await match.getByRole("button", { name: /Review reservation for/ }).click();
  await expect(match.locator(".notice")).toContainText(/simulated USDC/);
  await match.getByRole("button", { name: /Accept fixed terms for/ }).click();
  const png = await actor.evaluate(() => { const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 240; const context = canvas.getContext("2d")!; context.fillStyle = "green"; context.fillRect(0, 0, 320, 240); return canvas.toDataURL("image/png").split(",")[1]; });
  await actor.getByLabel("Choose an image").setInputFiles({ name: "synthetic-color.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await expect(actor.getByRole("checkbox")).toHaveCount(0);
  const firstUploadResponse = actor.waitForResponse(response => response.request().method() === "POST" && response.url().includes("/media?"));
  await actor.getByRole("button", { name: "Submit image", exact: true }).click();
  const firstUploaded = await (await firstUploadResponse).json();
  await expect(actor.getByText("queued", { exact: true })).toBeVisible();
  await expect(actor.getByText(/Checking your image with AI/)).toBeVisible();
  let protectedRetry = true;
  await actor.route(`**/submissions/${firstUploaded.id}`, async route => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      ...firstUploaded,
      fixture: false,
      state: "verification_pending",
      payment_confirmed: false,
      findings: {
        ...firstUploaded.findings,
        protected: protectedRetry,
        processing_error: protectedRetry ? "temporary media-provider failure" : "legacy automatic retries exhausted",
        verification: { decision: "retry", reason: protectedRetry ? "Pending automatic retry in five minutes." : "Automatic retries are exhausted; the obligation will release at its deadline, without payment.", threshold: 80 },
      },
    }) });
  });
  await actor.getByRole("button", { name: "Refresh submission status" }).click();
  const pendingUpload = actor.locator(".upload-box").filter({ hasText: "verification pending" });
  await expect(pendingUpload.getByText(/temporary media-provider failure.*Verification remains pending; no payment is authorized/)).toBeVisible();
  await expect(pendingUpload.locator(".error")).toHaveCount(0);
  protectedRetry = false;
  await actor.getByRole("button", { name: "Refresh submission status" }).click();
  await expect(pendingUpload.getByText(/legacy automatic retries exhausted.*Verification remains pending; no payment is authorized/)).toBeVisible();
  await expect(pendingUpload.locator(".error")).toHaveCount(0);
  await actor.unroute(`**/submissions/${firstUploaded.id}`);
  const root = path.resolve(__dirname, "../../..");
  const worker = spawnSync(process.env.PYTHON_BIN!, ["-m", "framebounty.worker", "--once"], { cwd: root, env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL }, encoding: "utf-8", timeout: 60000 });
  expect(worker.status, worker.stderr).toBe(0);
  await actor.getByRole("button", { name: "Refresh submission status" }).click();
  await expect(actor.getByLabel("AI verification results")).toContainText("pass");
  await buyer.getByRole("button", { name: "Refresh queue & coverage" }).click();
  await buyer.getByRole("button", { name: "View submitted image & AI checks" }).click();
  await expect(buyer.getByAltText("Submitted image")).toBeVisible();
  await expect(buyer.getByRole("checkbox")).toHaveCount(0);
  await buyer.getByRole("button", { name: "Release simulated funds", exact: true }).click();
  await expect(buyer.getByText(/FIXTURE SUBMISSION.*fixture accepted/)).toBeVisible();
  await actor.getByRole("button", { name: "Refresh submission status" }).click();
  await expect(actor.getByText("Simulated reward released; no blockchain payment occurred.", { exact: true })).toBeVisible();
  await expect(actor.getByText("Reward paid.", { exact: true })).toHaveCount(0);
  await actor.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "image-submission-mobile.png"), fullPage: true });
  await buyer.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "image-post-desktop.png"), fullPage: true });
  // A second fixture image fails automatically; the contributor sees rejection
  // and its reason without a buyer quality decision or refresh click.
  await actor.getByRole("button", { name: "Find work", exact: true }).click();
  await actor.locator(".agent-task").filter({ hasText: /cat climbing a tree/i }).getByRole("button", { name: /Review reservation for/ }).click();
  await actor.locator(".agent-task").filter({ hasText: /cat climbing a tree/i }).getByRole("button", { name: /Accept fixed terms for/ }).click();
  await actor.getByLabel("Choose an image").setInputFiles({ name: "synthetic-failure.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  const uploadResponse = actor.waitForResponse(response => response.request().method() === "POST" && response.url().includes("/media?"));
  await actor.getByRole("button", { name: "Submit image", exact: true }).click();
  const uploaded = await (await uploadResponse).json();
  const failedCard = actor.locator(".mine article.panel").filter({ hasText: uploaded.reservation_id.slice(0, 8) });
  const failingWorker = spawnSync(process.env.PYTHON_BIN!, ["-m", "framebounty.worker", "--once"], { cwd: root, env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL, FIXTURE_VERIFICATION_RESULT: "fail" }, encoding: "utf-8", timeout: 60000 });
  expect(failingWorker.status, failingWorker.stderr).toBe(0);
  await expect(failedCard).toContainText("verification rejected", { timeout: 10000 });
  await expect(failedCard).toContainText("confidence 100%");
  await buyerContext.close(); await actorContext.close();
});

async function installWallet(page: Page, rejectSignature = false) {
  const wallet = Wallet.createRandom();
  await page.exposeFunction(
    "testWalletRequest",
    async ({ method, params }: { method: string; params?: string[] }) => {
      if (method === "eth_requestAccounts") return [wallet.address];
      if (method === "eth_chainId") return "0x4cef52";
      if (method === "personal_sign" && rejectSignature)
        throw new Error("User rejected signature");
      if (method === "personal_sign")
        return wallet.signMessage(getBytes(params![0]));
      throw new Error(`Unexpected wallet method: ${method}`);
    },
  );
  await page.addInitScript(() => {
    const listeners = new Map<string, Set<() => void>>();
    Object.defineProperty(window, "ethereum", {
      value: {
        on: (name: string, callback: () => void) => {
          if (!listeners.has(name)) listeners.set(name, new Set());
          listeners.get(name)!.add(callback);
        },
        removeListener: (name: string, callback: () => void) =>
          listeners.get(name)?.delete(callback),
        emitTestEvent: (name: string) =>
          listeners.get(name)?.forEach((callback) => callback()),
        request: (args: unknown) =>
          (
            window as unknown as {
              testWalletRequest: (args: unknown) => unknown;
            }
          ).testWalletRequest(args),
      },
    });
  });
}

async function connect(page: Page) {
  await installWallet(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Connect wallet" }).click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
}

async function installCamera(page: Page, videoPath: string, denyFirst = false) {
  const base64 = readFileSync(videoPath).toString("base64");
  await page.addInitScript(({ bytes, denyOnce }) => {
    let attempts = 0;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async (constraints: MediaStreamConstraints) => {
          attempts += 1;
          if (denyOnce && attempts === 1)
            throw new DOMException("Camera permission denied for regression", "NotAllowedError");
          if (constraints.audio !== false) throw new Error("Camera capture must not request audio");
          return new MediaStream();
        },
      },
    });
    class FixtureRecorder {
      static isTypeSupported(type: string) { return type === "video/mp4"; }
      state: RecordingState = "inactive";
      mimeType = "video/mp4";
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
        this.mimeType = options?.mimeType || "video/mp4";
      }
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        const binary = atob(bytes);
        const data = Uint8Array.from(binary, character => character.charCodeAt(0));
        const blob = new Blob([data], { type: this.mimeType });
        queueMicrotask(() => {
          this.ondataavailable?.({ data: blob } as BlobEvent);
          this.onstop?.();
        });
      }
    }
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FixtureRecorder });
  }, { bytes: base64, denyOnce: denyFirst });
}

function expireToken(authorization: string) {
  const result = spawnSync(
    process.env.PYTHON_BIN!,
    [
      "-c",
      "import os,hashlib; from sqlalchemy import create_engine,text; e=create_engine(os.environ['E2E_DATABASE_URL']); c=e.connect(); c.execute(text(\"UPDATE auth_sessions SET expires_at=now()-interval '1 second' WHERE token_hash=:hash\"),{'hash':hashlib.sha256(os.environ['E2E_EXPIRE_TOKEN'].encode()).hexdigest()}); c.commit(); c.close(); e.dispose()",
    ],
    {
      env: { ...process.env, E2E_EXPIRE_TOKEN: authorization.slice(7) },
      encoding: "utf-8",
      timeout: 15000,
    },
  );
  expect(result.status, result.stderr).toBe(0);
}

test("a buyer's cup post reaches a contributor who only says they have a cup", async ({ browser }) => {
  const buyer = await (await browser.newContext()).newPage();
  const contributor = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await connect(buyer);
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("I want 2 videos of a person pouring water into a cup under 2 USDC");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  await expect(buyer.getByRole("region", { name: "Generated post preview" })).toBeVisible();
  await buyer.getByText("More options", { exact: true }).click();
  await buyer.getByRole("button", { name: "Save draft instead" }).click();
  await buyer.getByRole("button", { name: "Publish simulated post" }).click();
  await expect(buyer.getByText(/Open.*Simulated funding/)).toBeVisible();
  await connect(contributor);
  await contributor.getByRole("button", { name: "Contributor workspace" }).click();
  await contributor.getByLabel("Message your work agent").fill("I have a cup and no time limit");
  await contributor.getByRole("button", { name: "Send", exact: true }).click();
  await expect(contributor.getByText(/Matching on: cup\./)).toBeVisible();
  await expect(contributor.getByText(/no matches|couldn't find matching/i)).toHaveCount(0);
  const task = contributor.locator(".agent-task").filter({ hasText: /pouring water into a cup/i });
  await expect(task.getByRole("button", { name: /Review reservation for/ })).toBeVisible();
});

for (const batchCount of [1, 2]) test(`image folder selection submits chosen count ${batchCount} to separate reservations`, async ({ browser }) => {
  const buyer = await (await browser.newContext()).newPage();
  const actor = await (await browser.newContext()).newPage();
  await connect(buyer);
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("I want 2 images of red circles under 2 USDC");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  await expect(buyer.getByRole("region", { name: "Generated post preview" })).toBeVisible();
  await buyer.getByText("More options", { exact: true }).click();
  await buyer.getByRole("button", { name: "Save draft instead" }).click();
  await buyer.getByRole("button", { name: "Publish simulated post" }).click();
  await connect(actor);
  await actor.getByRole("button", { name: "Contributor workspace" }).click();
  await actor.getByLabel("Message your work agent").fill("Show me what's open");
  await actor.getByRole("button", { name: "Send", exact: true }).click();
  const task = actor.locator(".agent-task").filter({ hasText: /red circles/i });
  await task.getByLabel(/Images to submit/).fill("2");
  await task.getByRole("button", { name: /Review reservation for/ }).click();
  await task.getByRole("button", { name: /Accept fixed terms for/ }).click();
  const batch = actor.getByRole("region", { name: "Upload image batch" });
  await expect(batch).toContainText("2 confirmed image reservations");
  const image = await actor.evaluate(() => { const c = document.createElement("canvas"); c.width = 120; c.height = 180; c.getContext("2d")!.fillRect(0, 0, 120, 180); return c.toDataURL().split(",")[1]; });
  const folder = path.join(path.dirname(process.env.E2E_VIDEO!), `batch-images-${batchCount}`);
  mkdirSync(folder);
  writeFileSync(path.join(folder, "a.png"), Buffer.from(image, "base64"));
  writeFileSync(path.join(folder, "b.png"), Buffer.from(image, "base64"));
  writeFileSync(path.join(folder, "ignore.txt"), "not an image");
  await batch.getByLabel("Choose image folder").setInputFiles(folder);
  await expect(batch.getByLabel("Number of images to submit")).toHaveValue("2");
  await batch.getByLabel("Number of images to submit").fill(String(batchCount));
  const uploads: string[] = [];
  actor.on("request", r => { if (r.method() === "POST" && r.url().includes("/image?")) uploads.push(r.url()); });
  if (batchCount === 2) {
    let requests = 0;
    await actor.route("**/reservations/*/image?*", async route => {
      if (++requests === 2) await route.fulfill({ status: 503, json: { detail: "Temporary second-image failure" } });
      else await route.continue();
    });
    await batch.getByRole("button", { name: "Submit 2 images", exact: true }).click();
    await expect(batch.getByRole("alert")).toContainText("Temporary second-image failure");
    await batch.getByRole("button", { name: "Continue image batch", exact: true }).click();
    await expect(batch).toHaveCount(0);
    expect(uploads).toHaveLength(3);
    expect(uploads[0]).not.toBe(uploads[1]);
    expect(uploads[1]).toBe(uploads[2]);
    return;
  }
  await batch.getByRole("button", { name: "Submit 1 images", exact: true }).click();
  await expect(batch).toContainText("1 confirmed image reservations");
  expect(uploads).toHaveLength(1);
  // The remaining reservation can accept another batch, without re-uploading
  // the first image or consuming both rewards for one uploaded file.
  await expect(batch.getByLabel("Or choose image files")).toBeEnabled();
  await batch.getByLabel("Or choose image files").setInputFiles({ name: "remaining.png", mimeType: "image/png", buffer: Buffer.from(image, "base64") });
  await batch.getByRole("button", { name: "Submit 1 images", exact: true }).click();
  await expect(batch).toHaveCount(0);
  expect(uploads).toHaveLength(2);
  expect(new Set(uploads).size).toBe(2);
});

test("buyer can remove an unpublished unfunded post from collections", async ({ page }) => {
  await connect(page);
  await page.getByLabel("Describe your task").filter({ visible: true }).fill("I want 1 video of a person filling an orange glass under 5 USDC");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("region", { name: "Generated post preview" })).toBeVisible();
  await page.getByText("More options", { exact: true }).click();
  await page.getByRole("button", { name: "Save draft instead" }).click();
  await page.getByRole("button", { name: "View my posts & status" }).click();
  const card = page.locator(".post-card").filter({ hasText: /orange glass/i });
  await expect(card).toContainText("Draft");
  await card.click();
  await page.getByRole("button", { name: "Remove unfunded post", exact: true }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "Refresh posts", exact: true }).click();
  await expect(card).toHaveCount(0);
});

test("anonymous visitors see sign-in only and cannot access product services", async ({
  page,
}) => {
  const productRequests: string[] = [];
  page.on("request", (req) => {
    if (/\/(tasks|me|agent-sessions|jobs)(\/|\?|$)/.test(req.url()))
      productRequests.push(req.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Buyer workspace" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Send buyer message" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Find matching tasks/ }),
  ).toHaveCount(0);
  expect(productRequests).toHaveLength(0);
  const denied = await page.request.get(
    (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8002") + "/tasks",
  );
  expect(denied.status()).toBe(401);
  await page.screenshot({
    path: path.join(path.dirname(process.env.E2E_VIDEO!), "signin-desktop.png"),
    fullPage: true,
  });
});

test("declining a wallet signature never opens the workspace", async ({
  page,
}) => {
  await installWallet(page, true);
  await page.goto("/");
  await page.getByRole("button", { name: "Connect wallet" }).click();
  await expect(
    page.getByRole("alert", { name: "Sign-in error" }),
  ).toContainText("User rejected signature");
  await expect(
    page.getByRole("button", { name: "Buyer workspace" }),
  ).toHaveCount(0);
});

test("signing out revokes the actual server token and removes product controls", async ({
  page,
}) => {
  const authenticated = page.waitForRequest((req) =>
    req.url().endsWith("/me/overview"),
  );
  await connect(page);
  const authorization = (await authenticated).headers()["authorization"];
  expect(Boolean(authorization)).toBe(true);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create collection", exact: true }),
  ).toHaveCount(0);
  await expect
    .poll(async () =>
      (
        await page.request.get(
          (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8002") +
            "/tasks",
          { headers: { Authorization: authorization } },
        )
      ).status(),
    )
    .toBe(401);
});

test("expired server sessions return the user to sign-in", async ({ page }) => {
  const authenticated = page.waitForRequest((req) =>
    req.url().endsWith("/me/overview"),
  );
  await connect(page);
  const authorization = (await authenticated).headers()["authorization"];
  const expire = spawnSync(
    process.env.PYTHON_BIN!,
    [
      "-c",
      "import os,hashlib; from sqlalchemy import create_engine,text; e=create_engine(os.environ['E2E_DATABASE_URL']); c=e.connect(); c.execute(text(\"UPDATE auth_sessions SET expires_at=now()-interval '1 second' WHERE token_hash=:hash\"),{'hash':hashlib.sha256(os.environ['E2E_EXPIRE_TOKEN'].encode()).hexdigest()}); c.commit(); c.close(); e.dispose()",
    ],
    {
      env: { ...process.env, E2E_EXPIRE_TOKEN: authorization.slice(7) },
      encoding: "utf-8",
      timeout: 15000,
    },
  );
  expect(expire.status, expire.stderr).toBe(0);
  await page.getByRole("button", { name: "Refresh overview" }).click();
  await expect(
    page.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send buyer message" }),
  ).toHaveCount(0);
});

test("wallet account changes invalidate access and reloading requires sign-in", async ({
  page,
}) => {
  await connect(page);
  await page.evaluate(() =>
    (
      window as unknown as {
        ethereum: { emitTestEvent: (name: string) => void };
      }
    ).ethereum.emitTestEvent("accountsChanged"),
  );
  await expect(
    page.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Contributor workspace" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
});

test("buyer plan → fixture funding → confirmed mobile upload → real decode → final funds release → coverage/export", async ({
  browser,
}) => {
  const buyerContext = await browser.newContext();
  const contributorContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const buyer = await buyerContext.newPage();
  const contributor = await contributorContext.newPage();
  await installCamera(contributor, process.env.E2E_VIDEO!, true);
  const authenticatedBuyer = buyer.waitForRequest((req) =>
    req.url().endsWith("/me/overview"),
  );
  await connect(buyer);
  const buyerAuthorization = (await authenticatedBuyer).headers()[
    "authorization"
  ];
  await buyer.screenshot({
    path: path.join(
      path.dirname(process.env.E2E_VIDEO!),
      "buyer-dashboard.png",
    ),
    fullPage: true,
  });
  await buyer.getByLabel("Describe your task").filter({ visible: true }).fill("Plan 20 towel-folding videos with large towels and dark surfaces under 20 USDC");
  await buyer.getByRole("button", { name: "Send", exact: true }).click();
  await expect(buyer.getByRole("region", { name: "Generated post preview" })).toBeVisible();
  await buyer.getByText("More options", { exact: true }).click();
  await buyer.getByRole("button", { name: "Save draft instead" }).click();
  await buyer.getByRole("button", { name: "Publish simulated post" }).click();
  await expect(buyer.getByText(/Open.*Simulated funding/)).toBeVisible();
  await connect(contributor);
  await contributor
    .getByRole("button", { name: "Contributor workspace" })
    .click();
  await contributor.getByLabel("Message your work agent").fill("I have a phone, a towel and a dark table. I have 20 minutes.");
  await contributor.getByRole("button", { name: "Send", exact: true }).click();
  await contributor.locator(".agent-task").filter({ hasText: /towel-folding demonstrations/i }).getByRole("button", { name: /Review reservation for/ }).click();
  await contributor.locator(".agent-task").filter({ hasText: /towel-folding demonstrations/i }).getByRole("button", { name: /Accept fixed terms for/ }).click();
  await expect(contributor.locator('input[type="file"]')).toHaveCount(0);
  await contributor.getByRole("button", { name: "Open camera", exact: true }).click();
  await expect(contributor.locator(".camera-capture").getByRole("alert")).toContainText("Allow camera access");
  await contributor.getByRole("button", { name: "Open camera", exact: true }).click();
  await expect(contributor.getByLabel("Live camera preview")).toBeVisible();
  await contributor.getByRole("button", { name: "Start recording", exact: true }).click();
  await contributor.waitForTimeout(300);
  await contributor.getByRole("button", { name: "Stop recording", exact: true }).click();
  await expect(contributor.locator(".camera-capture").getByRole("alert")).toContainText("under 10 seconds");
  await expect(contributor.getByRole("button", { name: "Submit recording", exact: true })).toBeDisabled();
  await contributor.getByRole("button", { name: "Retake recording", exact: true }).click();
  await contributor.getByRole("button", { name: "Open camera", exact: true }).click();
  await contributor.getByRole("button", { name: "Start recording", exact: true }).click();
  await contributor.waitForTimeout(10100);
  await contributor.getByRole("button", { name: "Stop recording", exact: true }).click();
  await expect(contributor.getByLabel("Recorded video review")).toBeVisible();
  await expect(contributor.getByRole("checkbox")).toHaveCount(0);
  const recordedUpload = contributor.waitForRequest(request => request.method() === "POST" && request.url().includes("/media?"));
  await contributor.getByRole("button", { name: "Submit recording", exact: true }).click();
  expect((await recordedUpload).headers()["x-capture-token"]).toBeTruthy();
  await expect(contributor.getByText("queued", { exact: true })).toBeVisible();
  const root = path.resolve(__dirname, "../../..");
  const worker = spawnSync(
    process.env.PYTHON_BIN!,
    ["-m", "framebounty.worker", "--once"],
    {
      cwd: root,
      env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL },
      encoding: "utf-8",
      timeout: 60000,
    },
  );
  expect(worker.status, worker.stderr).toBe(0);
  expect(JSON.parse(worker.stdout).processed).toBe(true);
  await buyer
    .getByRole("button", { name: "Collections & review", exact: true })
    .click();
  await expect(buyer.getByText("Open for contributors", { exact: true })).toBeVisible();
  await buyer.locator(".post-card").click();
  await buyer
    .getByRole("button", { name: "View watermarked preview & AI checks" })
    .click();
  await expect(buyer.locator("video")).toHaveCount(0);
  await expect(buyer.locator(".sample-image")).toHaveCount(6);
  await expect(buyer.getByRole("checkbox")).toHaveCount(0);
  await buyer.getByRole("button", { name: "Release simulated funds", exact: true }).click();
  await expect(buyer.locator(".nav-count")).toHaveCount(0);
  await expect(
    buyer.getByText(/FIXTURE SUBMISSION.*fixture accepted/),
  ).toBeVisible();
  await expect(
    buyer.getByText("accepted items", { exact: true }).locator(".."),
  ).toContainText("1");
  await expect(buyer.locator(".post-card")).toContainText("3 available slots");
  const download = buyer.waitForEvent("download");
  await buyer.getByRole("button", { name: "Export accepted manifest" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^framebounty-.*\.json$/,
  );
  await contributor
    .getByRole("button", { name: "Refresh submission status" })
    .click();
  await expect(
    contributor
      .locator(".upload-box")
      .getByText("fixture accepted", { exact: true }),
  ).toBeVisible();
  await expect(
    contributor.getByRole("heading", { name: "fixture accepted", exact: true }),
  ).toBeVisible();
  await contributor.screenshot({
    path: path.join(
      path.dirname(process.env.E2E_VIDEO!),
      "contributor-mobile.png",
    ),
    fullPage: true,
  });
  expect(
    await contributor.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await buyer
    .getByRole("button", { name: "Hide submitted media" })
    .click();
  expireToken(buyerAuthorization);
  await buyer
    .getByRole("button", { name: "View watermarked preview & AI checks" })
    .click();
  await expect(
    buyer.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(buyer.locator("video")).toHaveCount(0);
  await buyerContext.close();
  await contributorContext.close();
});
