import { afterEach, expect, test, vi } from "vitest";
import { fetchHealth } from "./health";

afterEach(() => vi.unstubAllGlobals());
test("reads live health from API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"status":"ok"}')),
  );
  await expect(fetchHealth("live")).resolves.toEqual({ status: "ok" });
});
test("does not show failed service as ready", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("{}", { status: 503 })),
  );
  await expect(fetchHealth("ready")).rejects.toThrow("尚未就绪");
});
test("rejects incorrect health schema", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response('{"status":"unknown"}')),
  );
  await expect(fetchHealth("ready")).rejects.toThrow("无法识别");
});
