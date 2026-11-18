import { test, expect, Page } from "@playwright/test";
import { Wallet, getBytes } from "ethers";
import { spawnSync } from "node:child_process";
import path from "node:path";

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
  await buyer.getByRole("button", { name: "Send buyer message" }).click();
  await buyer
    .getByRole("button", { name: "Review proposed plan in editor" })
    .click();
  await buyer
    .getByLabel(
      "Requested usage rights (contributors must acknowledge these before submitting)",
    )
    .fill(
      "Synthetic browser-test fixture only. No human footage and no model quality claim.",
    );
  await buyer.getByLabel(/I confirm these version 1 draft terms/).check();
  await buyer.getByRole("button", { name: "Confirm & save draft" }).click();
  await buyer.getByLabel(/For local testing, simulate this budget/).check();
  await buyer
    .getByRole("button", { name: "Simulate funding & publish fixture tasks" })
    .click();
  await expect(
    buyer.getByText(/No blockchain transaction occurred/),
  ).toBeVisible();
  await connect(contributor);
  await contributor
    .getByRole("button", { name: "Contributor workspace" })
    .click();
  await contributor
    .getByRole("button", { name: "Send contributor message" })
    .click();
  await contributor
    .getByRole("button", { name: "Review agent reservation terms" })
    .click();
  await contributor
    .getByRole("button", { name: "Confirm agent task & reward", exact: true })
    .click();
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
  await buyer.getByRole("button", { name: "Load my collections" }).click();
  const collection = buyer.getByLabel("Collection", { exact: true });
  await expect(collection.locator("option")).toHaveCount(2);
  await collection.selectOption({ index: 1 });
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
    .getByLabel("The video shows a complete towel-folding demonstration.")
    .check();
  await buyer
    .getByLabel("Meets the buyer-approved large-towel definition.")
    .check();
  await buyer
    .getByLabel("Meets the buyer-approved dark-surface definition.")
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
    buyer.getByText("accepted clips", { exact: true }).locator(".."),
  ).toContainText("1");
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
    .getByRole("button", { name: "Hide private video & frames" })
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
