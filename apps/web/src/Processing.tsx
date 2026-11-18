import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  attachmentBlob,
  download,
  request,
  statusText,
  type Me,
  type Message,
  type Page,
  type ProcessingCapabilities,
  type ProcessingResult,
} from "./api";

const names: Record<string, string> = {
  ocr: "图片文字识别",
  asr: "语音转文字",
  embedding: "语义检索",
  llm: "AI 摘要与候选",
};
function failure(code: string | null | undefined): string {
  const names: Record<string, string> = {
    INVALID_IMAGE: "图片损坏或不是受支持的图片，原件仍然保留。",
    IMAGE_PIXEL_LIMIT: "图片像素超过识别限制，请先在本地生成适合识别的副本。",
    PROVIDER_TIMEOUT: "识别超时，可稍后重试或使用较小图片。",
    ANIMATED_IMAGE_UNSUPPORTED: "暂不识别动画，请提供静态图片副本。",
    PROVIDER_UNAVAILABLE: "本地引擎或模型尚未就绪。",
    PROVIDER_VERSION_CHANGED: "模型版本已变化，请重新发起识别以保留准确来源。",
    ATTACHMENT_MISSING: "原始附件缺失，无法识别。",
    UNSUPPORTED_AUDIO_CODEC: "语音格式不受支持或文件损坏，原始音频仍然保留。",
    AUDIO_DURATION_LIMIT:
      "语音长度超过本地转录限制，请使用较短的合法音频副本。",
  };
  return names[code || ""] || "处理未完成，原始消息和附件保持完整。";
}
function useCapabilities() {
  return useQuery({
    queryKey: ["processing-capabilities"],
    queryFn: () => request<ProcessingCapabilities>("/processing/capabilities"),
    refetchInterval: (query) =>
      Object.values(query.state.data?.modules || {}).some((module) =>
        ["queued", "running", "failed_retryable"].includes(
          module.install_job?.status || "",
        ),
      )
        ? 2000
        : false,
  });
}
export function ProcessingModules() {
  const capabilities = useCapabilities();
  const client = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function toggle(kind: string, enabled: boolean) {
    setError("");
    setBusy(kind);
    try {
      await request(`/processing/modules/${kind}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
      await client.invalidateQueries({ queryKey: ["processing-capabilities"] });
      await client.invalidateQueries({ queryKey: ["processing-results"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "设置未保存");
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="panel processing-modules">
      <h2>本地识别模块</h2>
      <p className="fine">
        默认关闭，由管理员明确启用。关闭后取消尚未完成的任务，保留原件和已有结果。
        下载模型需要联网，聊天内容仅在本地推理。模型下载完成后可离线使用。
      </p>
      {(error || capabilities.error) && (
        <div role="alert" className="error-box">
          {error || "无法读取模块状态"}
        </div>
      )}
      {Object.entries(capabilities.data?.modules || {}).map(
        ([kind, module]) => (
          <div className="module-row" key={kind}>
            <div>
              <strong>{names[kind] || kind}</strong>
              <p className="fine">
                {module.available
                  ? "本地引擎和模型已就绪"
                  : "本地引擎或模型尚未安装"}
              </p>
            </div>
            {!module.available && module.installable && (
              <button
                disabled={
                  busy === kind ||
                  ["queued", "running"].includes(
                    module.install_job?.status || "",
                  )
                }
                onClick={() => {
                  setBusy(kind);
                  setError("");
                  void request(`/processing/models/${kind}/install`, {
                    method: "POST",
                  })
                    .then(() => capabilities.refetch())
                    .catch((e) =>
                      setError(
                        e instanceof Error ? e.message : "模型安装未开始",
                      ),
                    )
                    .finally(() => setBusy(""));
                }}
              >
                {["queued", "running"].includes(
                  module.install_job?.status || "",
                )
                  ? "正在安装模型…"
                  : `下载并安装模型（约${Math.ceil((module.download_bytes || 0) / 1048576)}MB）`}
              </button>
            )}
            {module.install_job?.failure_code && (
              <span className="error-box">
                模型安装未完成，请检查网络与磁盘空间后重试。
              </span>
            )}
            <button
              disabled={busy === kind || (!module.enabled && !module.available)}
              onClick={() => void toggle(kind, !module.enabled)}
            >
              {module.enabled ? "关闭" : "启用"}
              {names[kind] || kind}
            </button>
          </div>
        ),
      )}
    </section>
  );
}

function Coordinates({ result }: { result: ProcessingResult }) {
  const [image, setImage] = useState("");
  const [word, setWord] = useState(0);
  const [error, setError] = useState("");
  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image);
    },
    [image],
  );
  const words = result.details.words || [];
  const selected = words[word];
  if (
    !result.attachment_id ||
    !words.length ||
    !result.details.width ||
    !result.details.height
  )
    return null;
  return (
    <div className="ocr-coordinates">
      {!image && (
        <button
          onClick={() =>
            attachmentBlob(result.attachment_id!)
              .then((blob) => setImage(URL.createObjectURL(blob)))
              .catch(() => setError("无法读取原图"))
          }
        >
          定位原图文字
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {image && (
        <>
          <svg
            role="img"
            aria-label="OCR原图与文字位置"
            viewBox={`0 0 ${result.details.width} ${result.details.height}`}
            className="ocr-image"
          >
            <image
              href={image}
              x="0"
              y="0"
              width={result.details.width}
              height={result.details.height}
            />
            {selected && (
              <rect
                className="ocr-selected-box"
                x={selected.bbox[0]}
                y={selected.bbox[1]}
                width={selected.bbox[2]}
                height={selected.bbox[3]}
              />
            )}
          </svg>
          <div className="ocr-words">
            {words.slice(0, 300).map((item, index) => (
              <button
                key={index}
                aria-pressed={word === index}
                onClick={() => setWord(index)}
              >
                {item.text}
              </button>
            ))}
          </div>
          <p className="fine">
            点击文字查看对应位置。识别评分 {selected?.confidence_raw.toFixed(1)}{" "}
            / 100，仅供核对。
            {words.length > 300
              ? "坐标列表展示前300个词，完整证据可导出。"
              : ""}
          </p>
        </>
      )}
    </div>
  );
}

function AudioEvidence({ result }: { result: ProcessingResult }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const player = useRef<HTMLAudioElement>(null);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  if (!result.attachment_id) return null;
  return (
    <div className="audio-evidence">
      <p className="fine">机器转录，请核对原语音。时间精度为片段级。</p>
      {!url && (
        <button
          onClick={() =>
            attachmentBlob(result.attachment_id!)
              .then((blob) => setUrl(URL.createObjectURL(blob)))
              .catch(() => setError("无法读取原语音"))
          }
        >
          核对原始语音
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {url && <audio ref={player} src={url} controls aria-label="原始语音" />}
      <div className="transcript-segments">
        {result.details.segments?.map((segment, index) => (
          <div key={index} className="transcript-segment">
            <button
              disabled={!url}
              onClick={() => {
                if (player.current) {
                  player.current.currentTime = segment.start;
                  void player.current
                    .play()
                    .catch(() => setError("请点击播放器播放"));
                }
              }}
            >
              {segment.start.toFixed(2)}s – {segment.end.toFixed(2)}s
            </button>
            <span>{segment.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ProcessingPanel({ message, me }: { message: Message; me: Me }) {
  const capabilities = useCapabilities();
  const client = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const results = useQuery({
    queryKey: ["processing-results", message.id],
    queryFn: () =>
      request<Page<ProcessingResult>>(
        `/processing/results?message_id=${message.id}`,
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some((r) =>
        ["queued", "running", "failed_retryable"].includes(r.status || ""),
      )
        ? 2000
        : false,
  });
  const resultStates = results.data?.items
    .map((r) => r.id + r.status)
    .join(":");
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["entities"] });
    void client.invalidateQueries({ queryKey: ["semantic-status"] });
  }, [client, resultStates]);
  const images = message.attachments.filter(
    (a) =>
      a.availability === "available" &&
      ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(
        a.mime_type,
      ),
  );
  const audios = message.attachments.filter(
    (a) =>
      a.availability === "available" &&
      ["audio/wav", "audio/ogg", "audio/flac", "audio/mpeg"].includes(
        a.mime_type,
      ),
  );
  const sources = [
    ...images.map((a) => ({ ...a, kind: "ocr" })),
    ...audios.map((a) => ({ ...a, kind: "asr" })),
  ];
  async function recognize(
    attachment: string | null,
    kind: string,
    sourceResult?: string,
  ) {
    setError("");
    setBusy(attachment || sourceResult || kind);
    try {
      await request("/process/" + kind, {
        method: "POST",
        body: JSON.stringify({
          message_id: message.id,
          attachment_id: attachment,
          source_result_id: sourceResult,
        }),
      });
      await results.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法发起识别");
    } finally {
      setBusy("");
    }
  }
  function aiActions(sourceResult?: string) {
    if (me.role === "reader" || message.privacy_scope !== "business_approved")
      return null;
    return (
      <div className="button-row">
        {(["embedding", "llm"] as const).map((kind) => (
          <button
            key={kind}
            disabled={
              !capabilities.data?.modules[kind]?.enabled ||
              !capabilities.data?.modules[kind]?.available ||
              !!busy
            }
            onClick={() => void recognize(null, kind, sourceResult)}
          >
            {kind === "embedding" ? "加入语义索引" : "AI 摘要与提取候选"}
          </button>
        ))}
      </div>
    );
  }
  return (
    <section className="processing-panel">
      <h3>本地识别、AI 与来源证据</h3>
      <p className="fine">
        本地处理。识别文字与原始消息分开保存，可检索、核对和导出。
      </p>
      {(error || results.error) && (
        <p className="error-box" role="alert">
          {error || "识别结果读取失败"}
        </p>
      )}
      <p className="fine">
        管理员可在「设置 → 本地识别模块」单独启用各模块。AI
        仅处理已获业务许可的会话。
      </p>
      {message.body_text && aiActions()}
      {me.role !== "reader" &&
        sources.map((a) => (
          <div className="module-row" key={a.id}>
            <span>{a.original_filename}</span>
            <button
              disabled={
                !capabilities.data?.modules[a.kind]?.enabled ||
                !capabilities.data?.modules[a.kind]?.available ||
                busy === a.id
              }
              onClick={() => void recognize(a.id, a.kind)}
            >
              {a.kind === "ocr" ? "识别图片文字" : "转录语音"}
            </button>
          </div>
        ))}
      {results.data?.items.map((result) => (
        <section className="processing-result" key={result.id}>
          <div className="module-row">
            <strong>
              {names[result.kind] || result.kind} ·{" "}
              {statusText(result.status || "queued")}
            </strong>
            <button
              onClick={() =>
                download(
                  `/processing/results/${result.id}`,
                  "recognition-evidence.json",
                ).catch((e) => setError(String(e)))
              }
            >
              导出识别证据
            </button>
          </div>
          {result.status === "completed" ? (
            <>
              <div className="recognized-text">
                {result.text ||
                  (result.kind === "llm"
                    ? "本次没有通过来源校验的摘要，请核对原文或尝试本地规则提取。"
                    : "未识别出文字，原始附件保持完整。")}
              </div>
              {result.kind === "ocr" ? (
                <Coordinates result={result} />
              ) : result.kind === "asr" ? (
                <AudioEvidence result={result} />
              ) : null}
              {["ocr", "asr"].includes(result.kind) &&
                result.text &&
                aiActions(result.id)}
              {result.kind === "llm" && (
                <p className="fine">
                  已生成 {result.details.entity_ids?.length || 0}{" "}
                  个待审核候选，请到「业务实体」逐字段核对。
                  {result.details.rejected_candidates?.length
                    ? ` ${result.details.rejected_candidates.length} 项输出因证据不足被拦截。`
                    : ""}
                </p>
              )}
              {result.kind === "embedding" && (
                <p className="fine">
                  已建立本地语义索引，可在搜索页按含义检索。
                </p>
              )}
              <details>
                <summary>查看识别来源与版本</summary>
                <dl>
                  <dt>原始附件 SHA-256</dt>
                  <dd className="mono">{result.source_sha256}</dd>
                  <dt>识别版本</dt>
                  <dd className="mono">{result.provider_version}</dd>
                </dl>
              </details>
            </>
          ) : result.failure_code ? (
            <p role="alert">{failure(result.failure_code)}</p>
          ) : (
            <p className="fine">
              {result.status === "cancelled"
                ? "任务已取消，原件保留。"
                : "后台正在处理，可以关闭详情后继续浏览。"}
            </p>
          )}
          {me.role === "admin" &&
            ["failed_permanent", "dead_letter", "cancelled"].includes(
              result.status || "",
            ) && (
              <button
                disabled={!capabilities.data?.modules[result.kind]?.enabled}
                onClick={() =>
                  request(`/jobs/${result.job_id}/retry`, { method: "POST" })
                    .then(() => results.refetch())
                    .catch((e) => setError(String(e)))
                }
              >
                重试识别
              </button>
            )}
        </section>
      ))}
      <button
        className="source-link"
        onClick={() => {
          void results.refetch();
          void client.invalidateQueries({ queryKey: ["search"] });
        }}
      >
        刷新识别结果
      </button>
    </section>
  );
}
