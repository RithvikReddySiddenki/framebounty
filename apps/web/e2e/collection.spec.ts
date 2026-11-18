import { test, expect, Page } from "@playwright/test";
import { Wallet, getBytes } from "ethers";
import { spawnSync } from "node:child_process";
import path from "node:path";

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

test("image request becomes a labeled post, private image submission, AI findings and human review", async ({ browser }) => {
  const buyerContext = await browser.newContext();
  const actorContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const buyer = await buyerContext.newPage();
  const actor = await actorContext.newPage();
  await connect(buyer);
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
  await actor.getByLabel("Message your work agent").fill("I have a phone");
  await actor.getByRole("button", { name: "Send", exact: true }).click();
  await expect(actor.getByText(/How much time do you have/)).toBeVisible();
  await expect(actor.getByLabel("Equipment (comma-separated)")).toHaveCount(0);
  await actor.getByLabel("Message your work agent").fill("20 minutes");
  await actor.getByRole("button", { name: "Send", exact: true }).click();
  const match = actor.locator(".agent-task").filter({ hasText: /cat climbing a tree/i });
  await expect(match.getByText("Image post", { exact: true })).toBeVisible();
  await actor.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "work-chat-mobile.png"), fullPage: true });
  await match.getByRole("button", { name: /Reserve for/ }).click();
  const png = await actor.evaluate(() => { const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 240; const context = canvas.getContext("2d")!; context.fillStyle = "green"; context.fillRect(0, 0, 320, 240); return canvas.toDataURL("image/png").split(",")[1]; });
  await actor.getByLabel("Choose an image").setInputFiles({ name: "synthetic-color.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await actor.getByLabel(/I have read and acknowledge/).check();
  await actor.getByRole("button", { name: "Upload image", exact: true }).click();
  await expect(actor.getByText("queued", { exact: true })).toBeVisible();
  const root = path.resolve(__dirname, "../../..");
  const worker = spawnSync(process.env.PYTHON_BIN!, ["-m", "framebounty.worker", "--once"], { cwd: root, env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL }, encoding: "utf-8", timeout: 60000 });
  expect(worker.status, worker.stderr).toBe(0);
  await actor.getByRole("button", { name: "Refresh submission status" }).click();
  await expect(actor.getByLabel("AI verification results")).toContainText("uncertain");
  await buyer.getByRole("button", { name: "Refresh queue & coverage" }).click();
  await buyer.getByRole("button", { name: "View submitted image & AI checks" }).click();
  await expect(buyer.getByAltText("Submitted image")).toBeVisible();
  await buyer.getByLabel("I inspected the full image.").check();
  await buyer.getByLabel("The submission meets the task described in this post.").check();
  await buyer.getByLabel("Clearly show a cat climbing a tree", { exact: true }).check();
  await buyer.getByLabel("Decision reason").fill("Synthetic UI workflow only; this image does not demonstrate a cat.");
  await buyer.getByRole("button", { name: "Accept fixture work" }).click();
  await expect(buyer.getByText(/FIXTURE SUBMISSION.*fixture accepted/)).toBeVisible();
  await actor.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "image-submission-mobile.png"), fullPage: true });
  await buyer.screenshot({ path: path.join(path.dirname(process.env.E2E_VIDEO!), "image-post-desktop.png"), fullPage: true });
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

test("buyer plan → fixture funding → confirmed mobile upload → real decode → human review → coverage/export", async ({
  browser,
}) => {
  const buyerContext = await browser.newContext();
  const contributorContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const buyer = await buyerContext.newPage();
  const contributor = await contributorContext.newPage();
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
  await buyer.getByRole("button", { name: "Save draft instead" }).click();
  await buyer.getByRole("button", { name: "Publish simulated post" }).click();
  await expect(buyer.getByText(/Open.*Simulated funding/)).toBeVisible();
  await connect(contributor);
  await contributor
    .getByRole("button", { name: "Contributor workspace" })
    .click();
  await contributor.getByLabel("Message your work agent").fill("I have a phone, a towel and a dark table. I have 20 minutes.");
  await contributor.getByRole("button", { name: "Send", exact: true }).click();
  await contributor.locator(".agent-task").filter({ hasText: /towel-folding demonstrations/i }).getByRole("button", { name: /Reserve for/ }).click();
  await contributor
    .getByLabel("Choose a phone video")
    .setInputFiles(process.env.E2E_VIDEO!);
  await contributor
    .getByLabel(/I have read and acknowledge these requested usage rights/)
    .check();
  await contributor
    .getByRole("button", { name: "Upload video", exact: true })
    .click();
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
    .getByRole("button", { name: "Watch full video & inspect frames" })
    .click();
  await buyer.locator("video").evaluate(async (element) => {
    await (element as HTMLVideoElement).play();
  });
  await expect
    .poll(() =>
      buyer
        .locator("video")
        .evaluate((element) => (element as HTMLVideoElement).currentTime),
    )
    .toBeGreaterThan(0);
  await buyer
    .locator("video")
    .evaluate((element) => (element as HTMLVideoElement).pause());
  await expect(buyer.locator(".sample-image")).toHaveCount(5);
  await buyer.getByLabel("I watched the full video.").check();
  await expect(
    buyer.getByRole("button", { name: "Accept fixture work" }),
  ).toBeDisabled();
  await buyer
    .getByLabel("The submission meets the task described in this post.")
    .check();
  await buyer
    .getByLabel(/large bath towel/i)
    .check();
  await buyer
    .getByLabel(/dark tabletop/i)
    .check();
  await buyer
    .getByLabel("Decision reason")
    .fill(
      "Synthetic workflow test attestation; this is not a quality evaluation.",
    );
  await buyer.getByRole("button", { name: "Accept fixture work" }).click();
  await expect(buyer.locator(".nav-count")).toHaveCount(0);
  await expect(
    buyer.getByText("FIXTURE SUBMISSION · fixture accepted"),
  ).toBeVisible();
  await expect(
    buyer.getByText("accepted items", { exact: true }).locator(".."),
  ).toContainText("1");
  await buyer.getByText("Ask the agent about this post", { exact: true }).click();
  await buyer
    .getByRole("textbox", { name: "Buyer message", exact: true })
    .last()
    .fill("Commission next batch");
  await buyer
    .getByRole("button", { name: "Send buyer message", exact: true })
    .last()
    .click();
  await expect(buyer.getByText(/2 fixture slots published/)).toBeVisible();
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
    .getByRole("button", { name: "Watch full video & inspect frames" })
    .click();
  await expect(
    buyer.getByRole("button", { name: "Connect wallet" }),
  ).toBeVisible();
  await expect(buyer.locator("video")).toHaveCount(0);
  await buyerContext.close();
  await contributorContext.close();
});
