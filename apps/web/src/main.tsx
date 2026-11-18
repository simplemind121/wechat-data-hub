import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";
import {
  request,
  setCsrf,
  download,
  statusText,
  dateText,
  attachmentBlob,
  type Me,
  type Page,
  type Message,
  type Conversation,
  type Overview,
  type Batch,
  type Review,
  type Audit,
  type Entity,
} from "./api";
import "./style.css";
import { ProcessingModules, ProcessingPanel } from "./Processing";
import { SemanticPanel } from "./Semantic";
import { OdooConnection } from "./Odoo";

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});
const icons: Record<string, string> = {
  概览: "◫",
  数据导入: "↥",
  会话: "▤",
  搜索: "⌕",
  审核队列: "⇄",
  业务实体: "▱",
  联系人: "♧",
  审计日志: "≡",
  设置: "◇",
};
function ErrorBox({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="error-box">
      {error instanceof Error ? error.message : "操作未完成，请重试"}
    </div>
  ) : null;
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span>▤</span>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span
      className={`badge ${["completed", "verified", "available"].includes(status) ? "success" : ["failed_permanent", "dead_letter", "conflicted"].includes(status) ? "danger" : ""}`}
    >
      {statusText(status)}
    </span>
  );
}
function Pager({
  next,
  loading,
  onMore,
}: {
  next: boolean;
  loading: boolean;
  onMore: () => void;
}) {
  return next ? (
    <button className="more" disabled={loading} onClick={onMore}>
      {loading ? "加载中…" : "加载更多"}
    </button>
  ) : null;
}
function usePages<T>(
  key: unknown[],
  path: string,
  enabled = true,
  poll?: number,
) {
  return useInfiniteQuery({
    queryKey: key,
    initialPageParam: "",
    enabled,
    refetchInterval: poll,
    queryFn: ({ pageParam }) =>
      request<Page<T>>(
        `${path}${path.includes("?") ? "&" : "?"}limit=30${pageParam ? "&cursor=" + pageParam : ""}`,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
}
function Brand() {
  return (
    <a className="brand" href="#">
      <span className="logo">
        W<span>·</span>
      </span>
      <span>
        WeChat
        <br />
        <b>DATA HUB</b>
      </span>
    </a>
  );
}
function Login({
  setup,
  onLogin,
}: {
  setup: boolean;
  onLogin: (me: Me) => void;
}) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const me = await request<Me>(setup ? "/auth/setup" : "/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
      setCsrf(me.csrf_token);
      onLogin(me);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <div className="auth-story">
        <Brand />
        <div>
          <div className="eyebrow">A PRIVATE HOME FOR YOUR HISTORY</div>
          <h1>
            记录有来处。
            <br />
            数据有归属。
          </h1>
          <p>
            把多设备导出记录归档到一个私有空间。
            <br />
            保留原始证据，审慎关联每一条消息。
          </p>
          <div className="auth-points">
            <span>✓ 本地处理</span>
            <span>✓ 来源可追溯</span>
            <span>✓ 无外部 AI</span>
          </div>
        </div>
        <small>WeChat Data Hub · 本地文件导入平台</small>
      </div>
      <main className="auth-form">
        <div className="auth-card">
          <span className="outline-tag">LOCAL FIRST</span>
          <h2>{setup ? "创建你的工作空间" : "欢迎回来"}</h2>
          <p>
            {setup
              ? "设置管理员账号，开始安全归档。"
              : "登录后继续查看你的记录。"}
          </p>
          <form onSubmit={submit}>
            {setup && (
              <label>
                工作空间名称
                <input
                  name="workspace_name"
                  defaultValue="我的工作空间"
                  required
                  maxLength={200}
                />
              </label>
            )}
            <label>
              用户名
              <input
                name="username"
                autoComplete="username"
                placeholder="至少 3 个字符"
                required
                minLength={3}
                maxLength={100}
              />
            </label>
            <label>
              密码
              <input
                name="password"
                type="password"
                autoComplete={setup ? "new-password" : "current-password"}
                placeholder="至少 12 个字符"
                required
                minLength={12}
                maxLength={200}
              />
            </label>
            <ErrorBox error={error} />
            <button className="primary wide" disabled={busy}>
              {busy ? "正在连接…" : setup ? "创建工作空间 →" : "登录工作空间 →"}
            </button>
          </form>
          <p className="fine">
            所有账号与聊天数据保存在本地。请只导入你有权处理的记录。
          </p>
        </div>
      </main>
    </div>
  );
}
function Dashboard({
  overview,
  navigate,
}: {
  overview: Overview | undefined;
  navigate: (page: string) => void;
}) {
  return (
    <>
      <div className="page-title">
        <div>
          <div className="eyebrow">YOUR DATA, YOUR CONTEXT</div>
          <h1>让每一条记录，都有来处。</h1>
          <p>统一归档，保留证据，在你的私有空间里重新连接上下文。</p>
        </div>
        <button className="primary" onClick={() => navigate("数据导入")}>
          ＋ 导入记录
        </button>
      </div>
      <section className="hero">
        <div>
          <span className="tag">私有工作空间</span>
          <h2>你的数据，留在你的掌控中</h2>
          <p>
            从合法导出的文件开始，保存不可覆盖的原件，
            <br />
            为每一条规范消息保留设备、批次与原始记录。
          </p>
          <button
            onClick={() => navigate(overview?.messages ? "会话" : "数据导入")}
          >
            {overview?.messages ? "浏览会话" : "开始第一次导入"} <span>↗</span>
          </button>
        </div>
        <div className="archive" aria-hidden="true">
          <div className="archive-back" />
          <div className="archive-front">
            <span>W</span>
            <small>PRIVATE ARCHIVE</small>
            <div>
              ••• ━━━━━
              <br />
              ••• ━━━
            </div>
          </div>
          <div className="archive-badge">✓ 原始证据优先</div>
        </div>
      </section>
      <div className="stats-grid">
        {[
          ["规范消息", overview?.messages, "条消息，来源可展开"],
          ["已归档会话", overview?.conversations, "独立的会话与隐私范围"],
          ["来源设备", overview?.devices, "保留设备和导出器版本"],
          ["待审核", overview?.pending_reviews, "相似记录交由你确认"],
        ].map(([label, count, note]) => (
          <article key={String(label)}>
            <span>{label}</span>
            <strong>
              {count === undefined ? "—" : Number(count).toLocaleString()}
            </strong>
            <small>{note}</small>
          </article>
        ))}
      </div>
      <div className="section-heading">
        <h2>继续整理你的记录</h2>
        <span>当前数据来自实际导入</span>
      </div>
      <div className="action-grid">
        <button onClick={() => navigate("会话")}>
          <i>▤</i>
          <h3>回到会话</h3>
          <p>按时间浏览，逐条查看来源。</p>
          <b>打开会话 →</b>
        </button>
        <button onClick={() => navigate("搜索")}>
          <i>⌕</i>
          <h3>找到关键信息</h3>
          <p>中文、型号与多条件组合检索。</p>
          <b>开始搜索 →</b>
        </button>
        <button onClick={() => navigate("审核队列")}>
          <i>⇄</i>
          <h3>复核相似记录</h3>
          <p>不自动合并弱匹配和重复文本。</p>
          <b>查看审核 →</b>
        </button>
      </div>
      <div className="note">
        <div>
          <h3>可追溯，不等于数据源完整</h3>
          <p>
            真实微信兼容范围取决于合法导出文件。官方加密备份不能直接当作结构化消息导入。
          </p>
        </div>
        <span className="outline-tag">LOCAL FIRST</span>
      </div>
    </>
  );
}
function ImportPage({ me, onImported }: { me: Me; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [manifest, setManifest] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const [coverage, setCoverage] = useState<unknown>();
  const [reportTitle, setReportTitle] = useState("来源覆盖报告");
  const needsSource =
    !!file && !file.name.toLowerCase().endsWith(".zip") && !manifest;
  const batches = usePages<Batch>(
    ["imports"],
    "/imports",
    me.role !== "reader",
    2000,
  );
  const rows = batches.data?.pages.flatMap((page) => page.items) || [];
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const form = new FormData();
      form.set("file", file);
      if (manifest) form.set("manifest", await manifest.text());
      if (needsSource) {
        const values = Object.fromEntries(
          new FormData(event.target as HTMLFormElement),
        );
        const mapping = String(values.field_mapping || "").trim();
        if (values.data_format === "csv-v1" && !mapping)
          throw new Error(
            "CSV 导入需要填写字段映射，请将标准字段对应到实际表头。",
          );
        form.set(
          "source",
          JSON.stringify({
            account_ref: values.account_ref,
            device_ref: values.device_ref,
            platform: values.platform,
            data_format: values.data_format,
            exporter_name: values.exporter_name || "unknown",
            exporter_version: values.exporter_version || "unknown",
            exported_at: new Date(String(values.exported_at)).toISOString(),
            original_timezone: values.original_timezone,
            field_mapping: mapping ? JSON.parse(mapping) : {},
          }),
        );
      }
      const result = await request<{ status: string }>("/imports", {
        method: "POST",
        body: form,
      });
      setNotice(
        result.status === "already_ingested"
          ? "这份原件已归档，未重复写入。"
          : "原件已归档，后台任务已排队。可在下方查看进度。",
      );
      await batches.refetch();
      onImported();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  async function action(path: string) {
    try {
      setError(null);
      await request(path, { method: "POST" });
      await batches.refetch();
    } catch (error) {
      setError(error);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>数据源与导入</h1>
          <p>保存原始字节、校验文件清单，持续追踪每次导入。</p>
        </div>
        {me.role === "admin" && (
          <button
            className="secondary"
            onClick={() =>
              download("/examples/bundle", "synthetic-example.zip").catch(
                setError,
              )
            }
          >
            ↓ 下载合成示例
          </button>
        )}
      </div>
      <ErrorBox error={error || batches.error} />
      {me.role === "reader" ? (
        <Empty title="当前账号仅有浏览权限" />
      ) : (
        <>
          {me.role === "admin" && (
            <form className="import-panel" onSubmit={submit}>
              <div className="upload-zone">
                <span>↥</span>
                <h2>选择导出文件</h2>
                <p>
                  推荐 ZIP：包含 manifest.json、JSONL / JSON / CSV
                  及相对路径媒体。
                  <br />
                  也可以分别选择一份数据文件和对应的 manifest.json。
                </p>
                <label className="file-label">
                  <input
                    aria-label="选择导出文件"
                    type="file"
                    accept=".zip,.jsonl,.json,.csv"
                    required
                    onChange={(event) => {
                      setFile(event.target.files?.[0] || null);
                      setNotice("");
                    }}
                  />
                </label>
                {file && (
                  <small>
                    {file.name} · {(file.size / 1024).toFixed(1)} KB
                  </small>
                )}
              </div>
              <div className="import-options">
                <h3>导入前确认</h3>
                <label>
                  单文件导入时附加清单
                  <input
                    aria-label="选择导入清单"
                    type="file"
                    accept=".json"
                    onChange={(event) =>
                      setManifest(event.target.files?.[0] || null)
                    }
                  />
                </label>
                {needsSource && (
                  <div className="source-fields">
                    <p className="fine">
                      没有清单时填写来源，本系统会实算大小和哈希。来源时间和字段映射需按实际导出填写。
                    </p>
                    <label>
                      格式
                      <select
                        name="data_format"
                        defaultValue={
                          file?.name.endsWith(".csv")
                            ? "csv-v1"
                            : file?.name.endsWith(".json")
                              ? "json-v1"
                              : "jsonl-v1"
                        }
                      >
                        <option value="jsonl-v1">JSONL v1（逐行消息）</option>
                        <option value="json-v1">JSON 数组 v1</option>
                        <option value="csv-v1">CSV v1（需下方映射）</option>
                      </select>
                    </label>
                    <label>
                      账号别名
                      <input
                        name="account_ref"
                        required
                        maxLength={200}
                        placeholder="例如：我的主账号"
                      />
                    </label>
                    <label>
                      设备别名
                      <input
                        name="device_ref"
                        required
                        maxLength={200}
                        placeholder="例如：我的 Mac"
                      />
                    </label>
                    <label>
                      来源平台
                      <select name="platform">
                        <option value="other">其他 / 未确认</option>
                        <option value="macos">macOS</option>
                        <option value="ios">iPhone / iOS</option>
                        <option value="windows">Windows</option>
                      </select>
                    </label>
                    <label>
                      来源时区
                      <input
                        name="original_timezone"
                        required
                        defaultValue={
                          Intl.DateTimeFormat().resolvedOptions().timeZone ||
                          "Asia/Shanghai"
                        }
                        placeholder="Asia/Shanghai"
                      />
                    </label>
                    <label>
                      实际导出时间
                      <input
                        name="exported_at"
                        type="datetime-local"
                        required
                      />
                    </label>
                    <label>
                      导出工具（不清楚填 unknown）
                      <input
                        name="exporter_name"
                        defaultValue="unknown"
                        maxLength={100}
                      />
                    </label>
                    <label>
                      导出工具版本
                      <input
                        name="exporter_version"
                        defaultValue="unknown"
                        maxLength={100}
                      />
                    </label>
                    <label>
                      字段映射 JSON（CSV 必填）
                      <textarea
                        name="field_mapping"
                        placeholder={
                          '{"conversation_ref":"会话", "sender_ref":"发送者", "sent_at":"时间", "body_text":"内容", "message_type":"类型"}'
                        }
                      />
                    </label>
                    <p className="fine">
                      标准字段：conversation_ref、sender_ref、sent_at、body_text、message_type、source_record_id。媒体文件请使用
                      ZIP。
                    </p>
                  </div>
                )}
                <div className="check-note">
                  ✓ 仅处理有权导入的数据
                  <br />✓ 清单需包含来源、时区、大小和 SHA-256
                  <br />✓ 重复原件不会重复写入
                  <br />✓ 缺失附件和异常记录会明确标注
                </div>
                <button className="primary wide" disabled={!file || busy}>
                  {busy ? "正在上传和归档…" : "校验并开始导入 →"}
                </button>
              </div>
            </form>
          )}
          {notice && (
            <div className="success-box" role="status">
              {notice}
            </div>
          )}
          <div className="section-heading">
            <h2>导入批次</h2>
            <span>后台处理期间自动刷新</span>
          </div>
          {!rows.length ? (
            <Empty title="还没有导入批次">
              <p>下载合成示例，即可先体验完整流程。</p>
            </Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>来源设备</th>
                    <th>导出器 / 平台</th>
                    <th>状态</th>
                    <th>归档时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((batch) => (
                    <tr key={batch.id}>
                      <td>
                        <strong>{batch.source.device_ref}</strong>
                        <small className="mono">{batch.id.slice(0, 8)}</small>
                      </td>
                      <td>
                        {batch.source.exporter_name}
                        <small>{batch.source.platform}</small>
                      </td>
                      <td>
                        <Badge
                          status={
                            batch.batch_status === "review_required"
                              ? batch.batch_status
                              : batch.job?.status || batch.batch_status
                          }
                        />
                        <small>
                          已处理 {batch.progress.processed.toLocaleString()} 条
                          · 异常 {batch.progress.quarantined.toLocaleString()}{" "}
                          条
                        </small>
                        {batch.job?.failure_code && (
                          <small>{batch.job.failure_code}</small>
                        )}
                      </td>
                      <td>{dateText(batch.created_at)}</td>
                      <td className="table-actions">
                        <button
                          onClick={() => {
                            setReportTitle("来源覆盖报告");
                            request(`/imports/${batch.id}/coverage`)
                              .then(setCoverage)
                              .catch(setError);
                          }}
                        >
                          覆盖报告
                        </button>
                        {me.role === "admin" && (
                          <button
                            onClick={() => {
                              setReportTitle("解析错误记录");
                              request(`/imports/${batch.id}/errors`)
                                .then(setCoverage)
                                .catch(setError);
                            }}
                          >
                            解析错误
                          </button>
                        )}
                        {me.role === "admin" && batch.job && (
                          <>
                            {[
                              "failed_retryable",
                              "failed_permanent",
                              "dead_letter",
                              "cancelled",
                            ].includes(batch.job.status) && (
                              <button
                                onClick={() =>
                                  action(`/imports/${batch.id}/retry`)
                                }
                              >
                                重试
                              </button>
                            )}
                            {["queued", "running", "failed_retryable"].includes(
                              batch.job.status,
                            ) && (
                              <button
                                onClick={() =>
                                  action(`/jobs/${batch.job!.id}/cancel`)
                                }
                              >
                                取消
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            next={!!batches.hasNextPage}
            loading={batches.isFetchingNextPage}
            onMore={() => void batches.fetchNextPage()}
          />
        </>
      )}
      {coverage !== undefined && (
        <Modal title={reportTitle} close={() => setCoverage(undefined)}>
          <p className="fine">
            指标以当前可观察导出文件为分母。尚未提供的真实设备信息不会推断补齐。
          </p>
          <pre>{JSON.stringify(coverage, null, 2)}</pre>
        </Modal>
      )}
    </>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  return (
    <div className="modal-backdrop" onClick={close}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="modal"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const items = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,a[href]",
            ),
          ).filter((node) => node.offsetParent !== null);
          const first = items[0],
            last = items[items.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button autoFocus aria-label="关闭详情" onClick={close}>
            ×
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function SourceDetail({
  id,
  close,
  me,
}: {
  id: string;
  close: () => void;
  me: Me;
}) {
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>();
  const detail = useQuery({
    queryKey: ["message", id],
    queryFn: () => request<Message>("/messages/" + id),
  });
  return (
    <Modal title="消息与来源证据" close={close}>
      <ErrorBox error={detail.error} />
      {detail.data ? (
        <>
          <div className="detail-body">
            {detail.data.body_text || "（非文本消息）"}
          </div>
          <ErrorBox error={error} />
          {notice && <div className="success-box">{notice}</div>}
          {me.role !== "reader" && (
            <div className="button-row">
              <button
                className="secondary"
                disabled={detail.data.privacy_scope !== "business_approved"}
                onClick={() =>
                  request("/entities/extract", {
                    method: "POST",
                    body: JSON.stringify({ message_id: id }),
                  })
                    .then(() => {
                      setNotice("已生成本地规则候选，请到业务实体页审核。");
                      void client.invalidateQueries({ queryKey: ["entities"] });
                    })
                    .catch(setError)
                }
              >
                提取报价候选
              </button>
              {detail.data.privacy_scope !== "business_approved" && (
                <span className="fine">
                  需先由管理员允许该会话进行业务处理。
                </span>
              )}
            </div>
          )}
          <p className="fine">
            原始时间：{detail.data.original_time_text || "未提供"} ·{" "}
            {statusText(detail.data.merge_status)}
          </p>
          <ProcessingPanel message={detail.data} me={me} />
          {detail.data.observations?.map((source, index) => (
            <section className="source-card" key={source.id}>
              <h3>
                来源 {index + 1} · {source.device.device_ref}
              </h3>
              <p>
                {source.device.platform} · {source.batch.adapter_id} v
                {source.batch.adapter_version}
              </p>
              <dl>
                <dt>原始定位</dt>
                <dd>{source.raw.source_record_locator}</dd>
                <dt>原始记录 SHA-256</dt>
                <dd className="mono">{source.raw.raw_sha256}</dd>
                <dt>原件 SHA-256</dt>
                <dd className="mono">{source.batch.sha256}</dd>
              </dl>
              <details>
                <summary>查看完整原始字段</summary>
                <pre>{JSON.stringify(source.raw.raw_payload, null, 2)}</pre>
              </details>
            </section>
          ))}
        </>
      ) : (
        <p>正在加载来源…</p>
      )}
    </Modal>
  );
}
function MessageCard({
  message,
  showSource,
}: {
  message: Message;
  showSource: (id: string) => void;
}) {
  const [error, setError] = useState<unknown>();
  const [preview, setPreview] = useState<{
    url: string;
    mime: string;
    name: string;
  } | null>(null);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview.url);
    },
    [preview],
  );

  return (
    <article className="message-card">
      <div className="avatar">{message.sender.slice(0, 1)}</div>
      <div className="message-content">
        <div className="message-meta">
          <strong>{message.sender}</strong>
          <time>{dateText(message.sent_at)}</time>
          <Badge status={message.merge_status} />
        </div>
        <div className="message-text">
          {message.body_text || `［${message.message_type}］`}
        </div>
        {message.processing_results
          ?.filter((r) => r.text)
          .map((result) => (
            <div className="derived-excerpt" key={result.id}>
              <span>
                {result.kind === "asr" ? "语音转录文字" : "图片识别文字"}
              </span>
              {result.text.slice(0, 500)}
            </div>
          ))}
        {message.reply_source_ref && (
          <div className="reply-note">
            ↳ 引用 {message.reply_to_id ? "已关联原消息" : "目标尚未导入"} ·{" "}
            {message.reply_source_ref}
          </div>
        )}
        {message.attachments.length > 0 && (
          <div className="attachment-list">
            {message.attachments.map((attachment, index) => (
              <div className="attachment-item" key={attachment.id + index}>
                <button
                  disabled={attachment.availability !== "available"}
                  onClick={() =>
                    download(
                      `/attachments/${attachment.id}/download`,
                      attachment.original_filename,
                    ).catch(setError)
                  }
                >
                  ▧ {attachment.original_filename}{" "}
                  <span>{statusText(attachment.availability)}</span>
                </button>
                {attachment.availability === "available" &&
                  [
                    "image/png",
                    "image/jpeg",
                    "image/gif",
                    "image/webp",
                    "audio/ogg",
                    "audio/wav",
                  ].includes(attachment.mime_type) && (
                    <button
                      className="preview-button"
                      onClick={() =>
                        attachmentBlob(attachment.id)
                          .then((blob) =>
                            setPreview({
                              url: URL.createObjectURL(blob),
                              mime: attachment.mime_type,
                              name: attachment.original_filename,
                            }),
                          )
                          .catch(setError)
                      }
                    >
                      预览
                    </button>
                  )}
              </div>
            ))}
          </div>
        )}
        <button className="source-link" onClick={() => showSource(message.id)}>
          ◈ {message.observation_count} 个来源 · 查看证据
        </button>
        <ErrorBox error={error} />
      </div>
      {preview && (
        <Modal title={preview.name} close={() => setPreview(null)}>
          {preview.mime.startsWith("image/") ? (
            <img
              className="media-preview"
              src={preview.url}
              alt={preview.name}
              onError={() =>
                setError(new Error("浏览器无法预览此文件，可下载原件查看"))
              }
            />
          ) : (
            <audio controls src={preview.url} />
          )}
        </Modal>
      )}
    </article>
  );
}
function Conversations({
  me,
  selected,
  select,
  showSource,
}: {
  me: Me;
  selected: string;
  select: (id: string) => void;
  showSource: (id: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<unknown>();
  const conversations = usePages<Conversation>(
    ["conversations", filter],
    "/conversations?q=" + encodeURIComponent(filter),
  );
  const rows = conversations.data?.pages.flatMap((page) => page.items) || [];
  const messages = usePages<Message>(
    ["messages", selected],
    `/conversations/${selected}/messages`,
    !!selected,
  );
  const current = rows.find((row) => row.id === selected);
  return (
    <>
      <div className="page-title">
        <div>
          <h1>会话与记录</h1>
          <p>统一时间线，原始记录与每一次来源观测都在。</p>
        </div>
        {me.role === "admin" && selected && (
          <button
            className="secondary"
            onClick={() =>
              download(
                "/exports/messages?format=jsonl&conversation_id=" + selected,
                "conversation.jsonl",
              ).catch(setError)
            }
          >
            ↓ 导出当前会话
          </button>
        )}
      </div>
      <ErrorBox error={error || conversations.error || messages.error} />
      <div className="conversation-layout">
        <section className="conversation-list">
          <div className="list-search">
            <input
              aria-label="筛选会话"
              placeholder="⌕ 筛选会话…"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>
          {rows.map((row) => (
            <button
              key={row.id}
              className={selected === row.id ? "selected" : ""}
              onClick={() => select(row.id)}
            >
              <span className="avatar">{row.title.slice(0, 1)}</span>
              <span>
                <strong>{row.title}</strong>
                <small>{row.preview || "暂无文本消息"}</small>
                <em>
                  {row.message_count} 条 ·{" "}
                  {row.privacy_scope === "private" ? "私人" : "已允许业务处理"}
                </em>
              </span>
            </button>
          ))}
          {!rows.length && (
            <Empty title="还没有会话">
              <p>导入后会在这里显示。</p>
            </Empty>
          )}
          <Pager
            next={!!conversations.hasNextPage}
            loading={conversations.isFetchingNextPage}
            onMore={() => void conversations.fetchNextPage()}
          />
        </section>
        <section className="timeline">
          {selected ? (
            <>
              <div className="timeline-head">
                <div>
                  <h2>{current?.title || "当前会话"}</h2>
                  <small>按发送时间排序 · 时间缺失的记录列于末尾</small>
                </div>
                {me.role === "admin" && current && (
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        await request(`/conversations/${current.id}/privacy`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            privacy_scope:
                              current.privacy_scope === "private"
                                ? "business_approved"
                                : "private",
                          }),
                        });
                        await conversations.refetch();
                      } catch (error) {
                        setError(error);
                      }
                    }}
                  >
                    {current.privacy_scope === "private"
                      ? "◇ 私人会话"
                      : "◇ 业务处理已允许"}
                  </button>
                )}
              </div>
              <div className="timeline-messages">
                {messages.data?.pages
                  .flatMap((page) => page.items)
                  .map((message) => (
                    <MessageCard
                      key={message.id}
                      message={message}
                      showSource={showSource}
                    />
                  ))}
                {messages.isPending && <p className="loading">加载消息中…</p>}
                <Pager
                  next={!!messages.hasNextPage}
                  loading={messages.isFetchingNextPage}
                  onMore={() => void messages.fetchNextPage()}
                />
              </div>
            </>
          ) : (
            <Empty title="选择一个会话">
              <p>在左侧选择会话，浏览消息与原始证据。</p>
            </Empty>
          )}
        </section>
      </div>
    </>
  );
}
function SearchPage({
  me,
  overview,
  showSource,
}: {
  me: Me;
  overview: Overview | undefined;
  showSource: (id: string) => void;
}) {
  const [params, setParams] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const result = usePages<Message>(
    ["search", params],
    "/search?" + params,
    submitted,
  );
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    for (const [key, value] of data)
      if (String(value))
        params.set(
          key,
          key === "start" || key === "end"
            ? new Date(String(value)).toISOString()
            : String(value),
        );
    setParams(params.toString());
    setSubmitted(true);
  }
  const rows = result.data?.pages.flatMap((page) => page.items) || [];
  return (
    <>
      <div className="page-title">
        <div>
          <h1>检索记录</h1>
          <p>从关键词到来源证据，缩小范围，找到完整上下文。</p>
        </div>
      </div>
      <SemanticPanel me={me} showSource={showSource} />
      <form className="search-panel" onSubmit={submit}>
        <div className="search-input">
          <span>⌕</span>
          <input
            name="q"
            aria-label="搜索关键词"
            placeholder="输入中文关键词、产品型号… 例如：M620 报价"
            maxLength={500}
          />
          <button className="primary">搜索记录</button>
        </div>
        <div className="filter-row">
          <label>
            消息类型
            <select name="message_type">
              <option value="">全部类型</option>
              {[
                "text",
                "image",
                "file",
                "audio",
                "video",
                "system",
                "unknown",
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            来源设备
            <select name="device_id">
              <option value="">全部设备</option>
              {overview?.sources.map((source) => (
                <option value={source.id} key={source.id}>
                  {source.device_ref}
                </option>
              ))}
            </select>
          </label>
          <label>
            起始时间
            <input type="datetime-local" name="start" />
          </label>
          <label>
            结束时间
            <input type="datetime-local" name="end" />
          </label>
          <label>
            附件
            <select name="has_attachment">
              <option value="">不限</option>
              <option value="true">包含附件引用</option>
              <option value="false">无附件引用</option>
            </select>
          </label>
        </div>
      </form>
      <ErrorBox error={result.error} />
      <div className="search-results">
        {!submitted ? (
          <Empty title="从一个关键词开始">
            <p>
              可组合来源、类型、日期与附件条件。多个关键词按“同时包含”匹配。
            </p>
          </Empty>
        ) : result.isPending ? (
          <p className="loading">正在检索…</p>
        ) : !rows.length ? (
          <Empty title="没有找到匹配的记录">
            <p>试试减少关键词或扩大筛选范围。</p>
          </Empty>
        ) : (
          <>
            {rows.map((message) => (
              <MessageCard
                key={message.id}
                message={message}
                showSource={showSource}
              />
            ))}
            <Pager
              next={!!result.hasNextPage}
              loading={result.isFetchingNextPage}
              onMore={() => void result.fetchNextPage()}
            />
          </>
        )}
      </div>
    </>
  );
}
function Reviews({
  me,
  showSource,
  refresh,
}: {
  me: Me;
  showSource: (id: string) => void;
  refresh: () => void;
}) {
  const [status, setStatus] = useState("pending");
  const [active, setActive] = useState<Review | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const reviews = usePages<Review>(
    ["reviews", status],
    "/reviews?status=" + status,
    me.role !== "reader",
  );
  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!active) return;
    setBusy(true);
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await request(`/reviews/${active.id}/resolve`, {
        method: "POST",
        body: JSON.stringify(data),
      });
      setActive(null);
      await reviews.refetch();
      refresh();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>审核队列</h1>
          <p>弱匹配保留为独立记录，由你复核；每项决定都进入审计。</p>
        </div>
        <select
          aria-label="审核状态"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="pending">待审核</option>
          <option value="deferred">已暂缓</option>
          <option value="resolved">已处理</option>
        </select>
      </div>
      <ErrorBox error={error || reviews.error} />
      {me.role === "reader" ? (
        <Empty title="当前账号没有审核权限" />
      ) : (
        <>
          {reviews.data?.pages
            .flatMap((page) => page.items)
            .map((review) => (
              <section className="review-card" key={review.id}>
                <div className="review-head">
                  <h3>
                    {review.review_type === "duplicate"
                      ? "相似消息 · 需要复核"
                      : review.review_type === "identity"
                        ? "同名联系人 · 不自动关联"
                        : "来源内容差异 · 保留独立版本"}
                  </h3>
                  <span className="mono">{review.id.slice(0, 8)}</span>
                </div>
                <div className="review-comparison">
                  {review.messages.map((message) => (
                    <MessageCard
                      key={message.id}
                      message={message}
                      showSource={showSource}
                    />
                  ))}
                  {review.contacts.map((contact) => (
                    <article key={contact.id}>
                      <h3>{contact.display_name}</h3>
                      <p className="mono">{contact.native_ref}</p>
                    </article>
                  ))}
                </div>
                {review.decision ? (
                  <p className="fine">
                    已处理：{review.decision.action} · {review.decision.reason}
                  </p>
                ) : (
                  <button
                    className="secondary"
                    onClick={() => {
                      setError(null);
                      setActive(review);
                    }}
                  >
                    复核并作出决定
                  </button>
                )}
              </section>
            ))}
          {reviews.data?.pages.every((page) => !page.items.length) && (
            <Empty title="当前没有需要处理的项目">
              <p>重复导入不会产生额外记录；相似消息会在这里等待确认。</p>
            </Empty>
          )}
          <Pager
            next={!!reviews.hasNextPage}
            loading={reviews.isFetchingNextPage}
            onMore={() => void reviews.fetchNextPage()}
          />
        </>
      )}
      {active && (
        <Modal title="记录审核决定" close={() => setActive(null)}>
          <form onSubmit={decide}>
            <p>相同文本可能确实发送过两次。请先查看完整来源，确认后再合并。</p>
            <label>
              决定
              <select name="action">
                <option value="reject">保留独立记录 / 拒绝关联</option>
                <option value="defer">暂缓处理</option>
                {active.review_type !== "conflict" && (
                  <option value="merge">确认是同一条消息 / 同一联系人</option>
                )}
              </select>
            </label>
            <label>
              复核理由
              <textarea
                name="reason"
                required
                minLength={3}
                maxLength={2000}
                placeholder="填写决定依据，至少3个字符"
              />
            </label>
            <ErrorBox error={error} />
            <button className="primary" disabled={busy}>
              {busy ? "保存中…" : "保存审核决定"}
            </button>
          </form>
        </Modal>
      )}
    </>
  );
}
function Contacts() {
  const contacts = usePages<{
    id: string;
    display_name: string;
    native_ref: string;
    aliases: { name: string }[];
    linked_contact_id: string | null;
  }>(["contacts"], "/contacts");
  return (
    <>
      <div className="page-title">
        <div>
          <h1>联系人</h1>
          <p>以来源身份区分联系人，同名昵称不会自动合并。</p>
        </div>
      </div>
      <ErrorBox error={contacts.error} />
      <div className="contact-grid">
        {contacts.data?.pages
          .flatMap((page) => page.items)
          .map((contact) => (
            <article key={contact.id}>
              <span className="avatar">{contact.display_name.slice(0, 1)}</span>
              <h3>{contact.display_name}</h3>
              <p className="mono">{contact.native_ref}</p>
              <small>
                历史别名：
                {contact.aliases.map((alias) => alias.name).join("、")}
              </small>
              {contact.linked_contact_id && <Badge status="verified" />}
            </article>
          ))}
      </div>
      {contacts.data?.pages.every((page) => !page.items.length) && (
        <Empty title="导入后将建立来源联系人" />
      )}
      <Pager
        next={!!contacts.hasNextPage}
        loading={contacts.isFetchingNextPage}
        onMore={() => void contacts.fetchNextPage()}
      />
    </>
  );
}
function AuditPage() {
  const audit = usePages<Audit>(["audit"], "/audit");
  return (
    <>
      <div className="page-title">
        <div>
          <h1>审计日志</h1>
          <p>
            记录登录、导入、来源读取、审核和导出。日志不保存密码或聊天正文。
          </p>
        </div>
      </div>
      <ErrorBox error={audit.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>动作</th>
              <th>对象</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {audit.data?.pages
              .flatMap((page) => page.items)
              .map((row) => (
                <tr key={row.id}>
                  <td>{dateText(row.created_at)}</td>
                  <td>{row.event_type}</td>
                  <td className="mono">{row.object_id?.slice(0, 12) || "—"}</td>
                  <td>{row.result}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <Pager
        next={!!audit.hasNextPage}
        loading={audit.isFetchingNextPage}
        onMore={() => void audit.fetchNextPage()}
      />
    </>
  );
}
function SettingsPage({ me }: { me: Me }) {
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const users = useQuery({
    queryKey: ["users"],
    enabled: me.role === "admin",
    queryFn: () =>
      request<{ items: { id: string; username: string; role: string }[] }>(
        "/users",
      ),
  });
  async function addUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setError(null);
    try {
      await request("/users", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      form.reset();
      setNotice("账号已创建。");
      await users.refetch();
    } catch (error) {
      setError(error);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>设置与隐私</h1>
          <p>私有部署，权限分工，按明确授权使用数据。</p>
        </div>
      </div>
      <ErrorBox error={error || users.error} />
      {notice && <div className="success-box">{notice}</div>}
      <div className="settings-grid">
        {me.role === "admin" && <ProcessingModules />}
        {me.role === "admin" && <OdooConnection />}
        {me.role === "admin" && <BackupPanel />}
        <section className="panel">
          <h2>当前工作空间</h2>
          <dl>
            <dt>账号</dt>
            <dd>{me.user.username}</dd>
            <dt>权限</dt>
            <dd>{me.role}</dd>
            <dt>数据处理</dt>
            <dd>本地文件 · 原件不可覆盖</dd>
            <dt>外部服务</dt>
            <dd>本地识别模块可单独启用；外部同步未启用</dd>
          </dl>
          <p className="fine">
            真实微信版本兼容性尚未通过样本验证。当前支持本系统明确契约的 JSONL /
            JSON / CSV；不解析微信官方加密备份。
          </p>
          {me.role === "admin" && (
            <div className="button-row">
              <button
                className="secondary"
                onClick={() =>
                  download(
                    "/exports/messages?format=jsonl",
                    "messages.jsonl",
                  ).catch(setError)
                }
              >
                ↓ 导出全部 JSONL
              </button>
              <button
                className="secondary"
                onClick={() =>
                  download(
                    "/exports/messages?format=csv",
                    "messages.csv",
                  ).catch(setError)
                }
              >
                ↓ 导出全部 CSV
              </button>
            </div>
          )}
        </section>
        {me.role === "admin" && (
          <section className="panel">
            <h2>工作空间成员</h2>
            <div className="member-list">
              {users.data?.items.map((user) => (
                <div key={user.id}>
                  <strong>{user.username}</strong>
                  <span>{user.role}</span>
                </div>
              ))}
            </div>
            <form onSubmit={addUser}>
              <label>
                新用户名
                <input name="username" required minLength={3} maxLength={100} />
              </label>
              <label>
                初始密码
                <input
                  name="password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={200}
                />
              </label>
              <label>
                角色
                <select name="role">
                  <option value="reader">reader · 仅浏览</option>
                  <option value="reviewer">reviewer · 浏览与审核</option>
                  <option value="admin">admin · 管理员</option>
                </select>
              </label>
              <button className="primary">创建账号</button>
            </form>
          </section>
        )}
      </div>
    </>
  );
}
function EntitiesPage({
  me,
  showSource,
}: {
  me: Me;
  showSource: (id: string) => void;
}) {
  const entities = usePages<Entity>(["entities"], "/entities");
  const [error, setError] = useState<unknown>();
  const [editing, setEditing] = useState<Entity | null>(null);
  const [preview, setPreview] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    const corrections: Record<string, string> = {};
    for (const evidence of editing.evidence) {
      const value = data.get("span_" + evidence.field);
      if (value !== null && value !== evidence.source_span)
        corrections[evidence.field] = String(value);
    }
    try {
      await request(`/entities/${editing.id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          decision: data.get("decision"),
          reason: data.get("reason"),
          corrections,
        }),
      });
      setEditing(null);
      await entities.refetch();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>业务实体</h1>
          <p>候选和批准事实分开保存，每一个字段都有可点击的来源。</p>
        </div>
      </div>
      <div className="note">
        <div>
          <h3>本地规则与 AI 候选 · 人工复核</h3>
          <p>
            规则或本地 AI
            可从消息、图片识别和语音转录中提出候选。所有字段必须有来源证据，且只处理管理员允许的业务会话；Odoo
            预览不会执行外部写入。
          </p>
        </div>
      </div>
      <ErrorBox error={error || entities.error} />
      {entities.data?.pages
        .flatMap((page) => page.items)
        .map((entity) => (
          <section className="panel entity-card" key={entity.id}>
            <div className="review-head">
              <h2>
                {(
                  {
                    quotation: "报价",
                    customer: "客户",
                    supplier: "供应商",
                    product: "产品",
                    purchase_intent: "采购意向",
                    order_candidate: "订单",
                    task: "任务",
                  } as Record<string, string>
                )[entity.entity_type] || entity.entity_type}
                候选 ·{" "}
                {entity.payload.product_model ||
                  entity.payload.name ||
                  entity.payload.company_name ||
                  "待核对"}
              </h2>
              <span className="badge">
                {entity.review_status === "approved"
                  ? "已批准"
                  : entity.review_status === "rejected"
                    ? "已拒绝"
                    : "待审核"}
              </span>
            </div>
            <dl>
              {Object.entries(entity.approved_payload || entity.payload).map(
                ([key, value]) => (
                  <div className="entity-field" key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </div>
                ),
              )}
            </dl>
            <div className="button-row">
              {[...new Set(entity.evidence.map((item) => item.message_id))].map(
                (id) => (
                  <button
                    key={id}
                    className="secondary"
                    onClick={() => showSource(id)}
                  >
                    ◈ 查看原消息证据
                  </button>
                ),
              )}
              {me.role !== "reader" && entity.review_status === "pending" && (
                <button
                  className="primary"
                  onClick={() => {
                    setError(null);
                    setEditing(entity);
                  }}
                >
                  编辑并审核
                </button>
              )}
              {me.role !== "reader" && entity.review_status === "approved" && (
                <button
                  className="secondary"
                  onClick={() =>
                    request("/integrations/odoo/dry-run", {
                      method: "POST",
                      body: JSON.stringify({ entity_ids: [entity.id] }),
                    })
                      .then(setPreview)
                      .catch(setError)
                  }
                >
                  Odoo 同步预览
                </button>
              )}
            </div>
            <p className="fine">提取版本：{entity.extractor_version}</p>
          </section>
        ))}
      {entities.data?.pages.every((page) => !page.items.length) && (
        <Empty title="还没有业务候选">
          <p>
            管理员允许会话进行业务处理后，在消息来源详情中点击“提取报价候选”。
          </p>
        </Empty>
      )}
      <Pager
        next={!!entities.hasNextPage}
        loading={entities.isFetchingNextPage}
        onMore={() => void entities.fetchNextPage()}
      />
      {editing && (
        <Modal title="业务字段审核" close={() => setEditing(null)}>
          <form onSubmit={review}>
            <p>
              修正必须直接取自来源消息或对应的 OCR/ASR
              文字；未经来源支持的字段会被拒绝。
            </p>
            {editing.evidence
              .filter((item) => item.field !== "supplier_ref")
              .map((item) => (
                <label key={item.field}>
                  {item.field} · 原文证据
                  <input
                    name={"span_" + item.field}
                    defaultValue={item.source_span}
                    required
                    maxLength={300}
                  />
                </label>
              ))}
            <label>
              决定
              <select name="decision">
                <option value="approve">批准已核对的字段</option>
                <option value="reject">拒绝此候选</option>
              </select>
            </label>
            <label>
              审核理由
              <textarea name="reason" minLength={3} maxLength={2000} required />
            </label>
            <ErrorBox error={error} />
            <button className="primary" disabled={busy}>
              {busy ? "保存中…" : "保存业务审核"}
            </button>
          </form>
        </Modal>
      )}
      {preview !== undefined && (
        <Modal title="Odoo 本地同步预览" close={() => setPreview(undefined)}>
          <p>
            仅预览草稿映射，不连接或写入
            Odoo。连接实例、供应商和产品映射仍需配置并验证。
          </p>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </Modal>
      )}
    </>
  );
}
function BackupPanel() {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  async function backup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(null);
    setDone(false);
    if (data.get("password") !== data.get("confirmation")) {
      setError(new Error("两次输入的备份口令不一致"));
      return;
    }
    setBusy(true);
    try {
      await download("/backups", "wechat-data-hub.wdhbak", {
        password: data.get("password"),
      });
      setDone(true);
      form.reset();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>加密备份</h2>
      <p className="fine">
        备份包含数据库、原件及账号。恢复时需提供口令，并使用全新数据库和目录。请将备份与口令分开保管。
      </p>
      <form onSubmit={backup}>
        <label>
          备份口令
          <input
            name="password"
            type="password"
            required
            minLength={16}
            maxLength={200}
            autoComplete="new-password"
            placeholder="至少16个字符"
          />
        </label>
        <label>
          再次输入口令
          <input
            name="confirmation"
            type="password"
            required
            minLength={16}
            maxLength={200}
            autoComplete="new-password"
          />
        </label>
        <ErrorBox error={error} />
        {done && (
          <div className="success-box">
            加密备份已下载。口令不会保存在服务器配置中。
          </div>
        )}
        <button className="primary" disabled={busy}>
          {busy ? "正在生成加密备份…" : "生成并下载加密备份"}
        </button>
      </form>
    </section>
  );
}
function Workspace({ me, logout }: { me: Me; logout: () => void }) {
  const [tab, setTab] = useState("概览");
  const [conversation, setConversation] = useState("");
  const [source, setSource] = useState("");
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => request<Overview>("/overview"),
    refetchInterval: 3000,
  });
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["messages"] });
    void client.invalidateQueries({ queryKey: ["conversations"] });
    void client.invalidateQueries({ queryKey: ["search"] });
  }, [
    overview.data?.messages,
    overview.data?.imports,
    overview.data?.running_jobs,
  ]);
  const tabs = Object.keys(icons).filter(
    (item) => !(["审计日志"].includes(item) && me.role !== "admin"),
  );
  function refresh() {
    void client.invalidateQueries({ queryKey: ["overview"] });
    void client.invalidateQueries({ queryKey: ["conversations"] });
  }
  return (
    <div className="layout">
      <aside>
        <Brand />
        <div className="nav-label">工作空间</div>
        <nav>
          {tabs.map((item) => (
            <button
              key={item}
              className={tab === item ? "active" : ""}
              aria-current={tab === item ? "page" : undefined}
              onClick={() => setTab(item)}
            >
              <span aria-hidden="true">{icons[item]}</span>
              {item}
              {item === "审核队列" && !!overview.data?.pending_reviews && (
                <b>{overview.data.pending_reviews}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="local">
          <span className="dot" />
          本地优先<span>无遥测 · 无外部 AI</span>
        </div>
      </aside>
      <div className="main">
        <header>
          <span>
            {me.workspace_name || "我的工作空间"}{" "}
            <span className="slash">/</span> {tab}
          </span>
          <div className="header-user">
            <span className="badge">{me.role}</span>
            <span>{me.user.username}</span>
            <button onClick={logout}>退出</button>
          </div>
        </header>
        <main>
          <ErrorBox error={overview.error} />
          {tab === "概览" && (
            <Dashboard overview={overview.data} navigate={setTab} />
          )}
          {tab === "数据导入" && <ImportPage me={me} onImported={refresh} />}
          {tab === "会话" && (
            <Conversations
              me={me}
              selected={conversation}
              select={setConversation}
              showSource={setSource}
            />
          )}
          {tab === "搜索" && (
            <SearchPage
              me={me}
              overview={overview.data}
              showSource={setSource}
            />
          )}
          {tab === "审核队列" && (
            <Reviews me={me} showSource={setSource} refresh={refresh} />
          )}
          {tab === "业务实体" && (
            <EntitiesPage me={me} showSource={setSource} />
          )}
          {tab === "联系人" && <Contacts />}
          {tab === "审计日志" && <AuditPage />}
          {tab === "设置" && <SettingsPage me={me} />}
          <footer>
            <span>WeChat Data Hub · 0.3.0</span>
            <span>原件保全 · 来源可追溯 · 本地优先</span>
          </footer>
        </main>
      </div>
      {source && (
        <SourceDetail id={source} close={() => setSource("")} me={me} />
      )}
    </div>
  );
}
function App() {
  const [me, setMe] = useState<Me | null>();
  const [setup, setSetup] = useState(false);
  const [error, setError] = useState<unknown>();
  async function load() {
    setError(null);
    try {
      const status = await request<{ setup_required: boolean }>("/auth/status");
      setSetup(status.setup_required);
      if (status.setup_required) setMe(null);
      else {
        try {
          const me = await request<Me>("/me");
          setCsrf(me.csrf_token);
          setMe(me);
        } catch {
          setMe(null);
        }
      }
    } catch (error) {
      setError(error);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function logout() {
    try {
      await request("/auth/logout", { method: "POST" });
      setCsrf("");
      client.clear();
      setMe(null);
    } catch (error) {
      setError(error);
    }
  }
  if (me === undefined)
    return (
      <div className="boot">
        <Brand />
        {error ? (
          <>
            <ErrorBox error={error} />
            <button className="secondary" onClick={() => void load()}>
              重新连接
            </button>
          </>
        ) : (
          <p>正在连接本地工作空间…</p>
        )}
      </div>
    );
  return me ? (
    <Workspace me={me} logout={() => void logout()} />
  ) : (
    <Login
      setup={setup}
      onLogin={(value) => {
        setSetup(false);
        setMe(value);
      }}
    />
  );
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <App />
  </QueryClientProvider>,
);
