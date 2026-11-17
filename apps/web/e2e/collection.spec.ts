import { test, expect, Page } from "@playwright/test";
import { Wallet, getBytes } from "ethers";
import { spawnSync } from "node:child_process";
import path from "node:path";

async function connect(page: Page) {
  const wallet = Wallet.createRandom();
  await page.exposeFunction(
    "testWalletRequest",
    async ({ method, params }: { method: string; params?: string[] }) => {
      if (method === "eth_requestAccounts") return [wallet.address];
      if (method === "eth_chainId") return "0x4cef52";
      if (method === "personal_sign")
        return wallet.signMessage(getBytes(params![0]));
      throw new Error(`Unexpected wallet method: ${method}`);
    },
  );
  await page.addInitScript(() => {
    Object.defineProperty(window, "ethereum", {
      value: {
        request: (args: unknown) =>
          (
            window as unknown as {
              testWalletRequest: (args: unknown) => unknown;
            }
          ).testWalletRequest(args),
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Connect wallet" }).click();
  await expect(page.getByRole("button", { name: /Disconnect/ })).toBeVisible();
}

test("buyer plan → fixture funding → confirmed mobile upload → real decode → human review → coverage/export", async ({
  browser,
}) => {
  const buyerContext = await browser.newContext();
  const contributorContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const buyer = await buyerContext.newPage();
  const contributor = await contributorContext.newPage();
  await connect(buyer);
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
    contributor.getByText("fixture accepted", { exact: true }),
  ).toBeVisible();
  await buyerContext.close();
  await contributorContext.close();
});
