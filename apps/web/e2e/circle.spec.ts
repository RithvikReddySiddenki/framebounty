import { test, expect } from "@playwright/test";

test("Circle callback failures show a safe provider code and allow retry", async ({ page }) => {
  // Exercise the real SDK's state-validation failure, without Google credentials
  // or pretending that a synthetic OAuth token can establish a valid session.
  await page.route("**/auth/config", route => route.fulfill({ json: {
    chain_id: 5042002, network: "Arc Testnet", real_money: false,
    circle_enabled: true, circle_app_id: "15ce9467-f481-54eb-aa59-d33d9dbca986",
    circle_login_method: "google", google_client_id: "test.apps.googleusercontent.com",
  } }));
  await page.addInitScript(() => {
    localStorage.setItem("socialLoginProvider", "Google");
    localStorage.setItem("state", "expected-state");
    sessionStorage.setItem("framebounty:circle:pending-login", JSON.stringify({
      deviceToken: "test-only", deviceEncryptionKey: "test-only",
      appId: "15ce9467-f481-54eb-aa59-d33d9dbca986", expiresAt: Date.now() + 600000,
    }));
  });
  await page.goto("/#state=wrong-state&id_token=invalid");
  await expect(page.getByRole("status")).toContainText("155140");
  await expect(page.getByRole("button", { name: "Continue with Google", exact: true })).toBeEnabled();
});
