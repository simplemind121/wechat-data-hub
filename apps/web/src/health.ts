export type Health = { status: "ok" | "ready" };

export async function fetchHealth(kind: "live" | "ready"): Promise<Health> {
  const response = await fetch(`/api/v1/health/${kind}`, { cache: "no-store" });
  if (!response.ok) throw new Error("服务尚未就绪");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) ||
    data.status !== (kind === "live" ? "ok" : "ready")
  )
    throw new Error("服务响应无法识别");
  return data as Health;
}
