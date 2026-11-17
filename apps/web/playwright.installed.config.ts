import { defineConfig } from "@playwright/test";

// Only point this at an isolated NEW synthetic validation deployment.
// These tests deliberately initialize an administrator and import synthetic files.
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: process.env.WDH_INSTALLED_URL ?? "http://127.0.0.1:15174",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    },
    trace: "retain-on-failure",
  },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/installed-results.json" }],
  ],
});
