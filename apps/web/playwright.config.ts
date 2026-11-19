import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 90000,
  use: {
    baseURL: "http://127.0.0.1:3002",
    viewport: { width: 1280, height: 900 },
    trace: "retain-on-failure",
  },
  reporter: "list",
});
