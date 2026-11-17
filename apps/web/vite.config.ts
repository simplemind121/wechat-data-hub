import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": process.env.WDH_API_PROXY_TARGET || "http://127.0.0.1:8000",
    },
  },
  test: { include: ["src/**/*.test.ts"] },
});
