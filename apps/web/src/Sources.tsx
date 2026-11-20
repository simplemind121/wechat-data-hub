import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { dateText, request } from "./api";

type Source = {
  id: string;
  name: string;
  kind: "personal_files" | "wecom_archive";
  enabled: boolean;
  credential_active: boolean;
  last_cursor: string | null;
  last_seen_at: string | null;
  failure_code: string | null;
  source_metadata: { account_ref: string; device_ref: string };
};

export function SourcesPanel() {
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => request<{ items: Source[] }>("/sources"),
    refetchInterval: 10000,
  });
  const [kind, setKind] = useState<Source["kind"]>("personal_files");
  const [credential, setCredential] = useState<{
    token: string;
    source: Source;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setCredential(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const result = await request<{ token: string; source: Source }>(
        "/sources",
        {
          method: "POST",
          body: JSON.stringify({
            name: data.get("name"),
            kind,
            metadata: {
              account_ref: data.get("account"),
              device_ref: data.get("device"),
              platform: data.get("platform"),
              wechat_version: data.get("version") || "unknown",
              exporter_name: data.get("exporter") || "user-export",
              exporter_version: data.get("exporter_version") || "unknown",
              data_format: data.get("format") || "jsonl-v1",
              field_mapping: JSON.parse(String(data.get("mapping") || "{}")),
            },
          }),
        },
      );
      setCredential(result);
      form.reset();
      await sources.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }
  async function change(path: string, body?: unknown) {
    setError("");
    setBusy(true);
    try {
      await request(path, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      await sources.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  function downloadConfig() {
    if (!credential) return;
    const config = {
      hub_url: "http://127.0.0.1:8000",
      token: credential.token,
      state_directory: "/collector/state",
      poll_seconds: 15,
      ...(credential.source.kind === "personal_files"
        ? { inbox: "/collector/inbox" }
        : {
            corp_id: "填写企业ID",
            archive_secret: "填写会话存档Secret",
            sdk_library: "/collector/secrets/libWeWorkFinanceSdk_C.so",
            private_keys: { "1": "/collector/secrets/archive-private.pem" },
          }),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(config, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download =
      credential.source.kind === "personal_files"
        ? "personal.json"
        : "wecom.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="panel">
      <h2>自动同步数据源</h2>
      <p>
        个人微信同步已导出的文件；企业微信使用官方会话存档。历史范围与媒体完整性取决于来源，登录状态不能证明历史已全部取得。
      </p>
      <form onSubmit={create}>
        <label>
          接入方式
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as Source["kind"])}
          >
            <option value="personal_files">个人微信 · 本地导出文件同步</option>
            <option value="wecom_archive">企业微信 · 官方会话存档</option>
          </select>
        </label>
        <div className="connector-grid">
          <label>
            数据源名称
            <input
              name="name"
              required
              maxLength={200}
              placeholder="例如：工作电脑"
            />
          </label>
          <label>
            微信账号别名
            <input
              name="account"
              required
              maxLength={200}
              placeholder="使用不含真实姓名的稳定别名"
            />
          </label>
          <label>
            来源设备标识
            <input
              name="device"
              required
              maxLength={200}
              placeholder="每个账号使用独立设备标识"
            />
          </label>
          <label>
            设备系统
            <select name="platform">
              <option value="windows">Windows</option>
              <option value="macos">macOS</option>
              <option value="other">Linux／其他</option>
              <option value="ios">iOS 导出</option>
            </select>
          </label>
          <label>
            微信版本
            <input
              name="version"
              placeholder="尚未确认可留空"
              maxLength={100}
            />
          </label>
        </div>
        {kind === "personal_files" ? (
          <>
            <div className="connector-grid">
              <label>
                导出工具名称
                <input
                  name="exporter"
                  defaultValue="user-export"
                  required
                  maxLength={100}
                />
              </label>
              <label>
                导出工具版本
                <input
                  name="exporter_version"
                  defaultValue="unknown"
                  required
                  maxLength={100}
                />
              </label>
              <label>
                单文件格式
                <select name="format">
                  <option value="jsonl-v1">JSONL</option>
                  <option value="json-v1">JSON 数组</option>
                  <option value="csv-v1">CSV（需字段映射）</option>
                </select>
              </label>
            </div>
            <label>
              CSV 字段映射（JSON；其他格式留空）
              <textarea
                name="mapping"
                placeholder={
                  '{"conversation_ref":"会话","sent_at":"时间","body_text":"内容"}'
                }
              />
            </label>
            <p className="fine">
              媒体 ZIP 根目录需有
              manifest.json，账号、设备、导出工具及版本应与这里一致。文件应写完后再放入同步目录。
            </p>
          </>
        ) : (
          <p className="fine">
            创建后在采集端配置企业 ID、存档 Secret、官方 SDK
            与对应版本的私钥。密钥保留在采集端，本页面不收集。实际企微账号尚待联调。
          </p>
        )}
        <button className="primary" disabled={busy}>
          创建数据源
        </button>
      </form>
      {credential && (
        <div className="note">
          <div>
            <h3>采集端配置仅本次可下载</h3>
            <p>
              保存到 collector/
              {credential.source.kind === "personal_files"
                ? "personal.json"
                : "wecom.json"}
              ，按运行手册启动对应采集端。配置含上传凭据，请保存在私有目录。
            </p>
            <button className="secondary" onClick={downloadConfig}>
              下载采集端配置
            </button>{" "}
            <button className="secondary" onClick={() => setCredential(null)}>
              已保存，关闭
            </button>
          </div>
        </div>
      )}
      {(error || sources.error) && (
        <p className="error-box" role="alert">
          {error || "数据源状态读取失败"}
        </p>
      )}
      {sources.data?.items.map((source) => (
        <article className="panel" key={source.id}>
          <h3>
            {source.name} ·{" "}
            {source.kind === "personal_files" ? "个人微信文件" : "企微存档"}
          </h3>
          <p>
            {source.enabled ? "允许同步" : "已暂停"} · 最近连接：
            {dateText(source.last_seen_at)}
          </p>
          <p className="fine">
            已归档位置：{source.last_cursor || "尚未接收数据"}
            。归档后可在下方导入批次查看解析结果。
            {source.failure_code && `采集异常：${source.failure_code}`}
          </p>
          <div className="button-row">
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void change(`/sources/${source.id}/state`, {
                  enabled: !source.enabled,
                })
              }
            >
              {source.enabled ? "暂停同步" : "恢复同步"}
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                setError("");
                void request<{ token: string }>(
                  `/sources/${source.id}/rotate`,
                  { method: "POST" },
                )
                  .then((result) =>
                    setCredential({ token: result.token, source }),
                  )
                  .catch((e) =>
                    setError(e instanceof Error ? e.message : "更换失败"),
                  )
                  .finally(() => setBusy(false));
              }}
            >
              更换采集凭据
            </button>
          </div>
        </article>
      ))}
      {sources.data?.items.length === 0 && (
        <p className="fine">尚未配置自动同步数据源，仍可使用下方手动导入。</p>
      )}
    </section>
  );
}
