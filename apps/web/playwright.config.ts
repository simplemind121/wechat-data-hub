import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:15173",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "../../.venv/bin/python ../../scripts/e2e_server.py",
      url: "http://127.0.0.1:18000/api/v1/health/live",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      env: { WDH_API_PROXY_TARGET: "http://127.0.0.1:18000" },
    },
  ],
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
});
