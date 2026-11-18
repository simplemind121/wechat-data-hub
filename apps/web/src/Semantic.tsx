import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, type Me, type ProcessingCapabilities } from "./api";

type Citation = {
  message_id: string;
  source_span: string;
  source_result_id?: string | null;
};
type Hit = { similarity: number; citation: Citation };
type Answer = { supported: boolean; answer: string; citations: Citation[] };
type IndexStatus = {
  eligible_messages: number;
  indexed_messages: number;
  pending_jobs: number;
};

export function SemanticPanel({
  me,
  showSource,
}: {
  me: Me;
  showSource: (id: string) => void;
}) {
  const capabilities = useQuery({
    queryKey: ["processing-capabilities"],
    queryFn: () => request<ProcessingCapabilities>("/processing/capabilities"),
  });
  const enabled = !!capabilities.data?.modules.embedding?.enabled;
  const status = useQuery({
    queryKey: ["semantic-status"],
    queryFn: () => request<IndexStatus>("/semantic/status"),
    enabled,
    refetchInterval: (q) => (q.state.data?.pending_jobs ? 2000 : false),
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  if (!enabled) return null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const question = String(data.get("question") || "");
    const action =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ||
      "search";
    setBusy(action);
    setError("");
    setAnswer(null);
    setHits(null);
    try {
      if (action === "ask")
        setAnswer(
          await request<Answer>("/semantic/ask", {
            method: "POST",
            body: JSON.stringify({ question }),
          }),
        );
      else
        setHits(
          (
            await request<{ items: Hit[] }>(
              "/semantic/search?" +
                new URLSearchParams({
                  q: question,
                  mode: data.get("hybrid") ? "hybrid" : "semantic",
                }),
            )
          ).items,
        );
    } catch (e) {
      setError(e instanceof Error ? e.message : "本地检索未完成");
    } finally {
      setBusy("");
    }
  }
  async function index() {
    setBusy("index");
    setError("");
    try {
      const result = await request<{
        queued: number;
        skipped: number;
        already_indexed: number;
        next_cursor: string | null;
      }>("/semantic/index", {
        method: "POST",
        body: JSON.stringify({ cursor, limit: 30 }),
      });
      setCursor(result.next_cursor);
      setNotice(
        `已排队 ${result.queued} 条，已索引 ${result.already_indexed} 条，跳过 ${result.skipped} 条。${result.next_cursor ? "可继续索引下一批。" : "已扫描到当前末尾。"}`,
      );
      await status.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法开始索引");
    } finally {
      setBusy("");
    }
  }
  function cite(c: Citation, i: number) {
    return (
      <div className="semantic-citation" key={`${c.message_id}-${i}`}>
        <blockquote>{c.source_span}</blockquote>
        <button onClick={() => showSource(c.message_id)}>
          查看引用 {i + 1} 的原消息{c.source_result_id ? "与识别证据" : ""}
        </button>
      </div>
    );
  }
  return (
    <section className="panel semantic-panel">
      <h2>按含义搜索与证据问答</h2>
      <p className="fine">
        仅检索已获业务处理许可且已索引的内容。问答返回来源摘录，机器识别和原消息中的数字仍需核对。
      </p>
      <div className="module-row">
        <span>
          已索引 {status.data?.indexed_messages || 0} /{" "}
          {status.data?.eligible_messages || 0} 条许可消息 · 待处理{" "}
          {status.data?.pending_jobs || 0} 项
        </span>
        {me.role !== "reader" && (
          <button disabled={!!busy} onClick={() => void index()}>
            {cursor ? "索引下一批消息" : "索引业务会话消息"}
          </button>
        )}
      </div>
      <p className="fine">
        图片和语音请先识别，再从消息详情将识别结果加入索引。
      </p>
      {notice && <p role="status">{notice}</p>}
      <form onSubmit={submit}>
        <label>
          语义问题
          <input
            name="question"
            aria-label="语义问题"
            placeholder="例如：M620 的报价是多少？"
            minLength={2}
            maxLength={250}
            required
          />
        </label>
        <label className="checkbox-row">
          <input type="checkbox" name="hybrid" defaultChecked />
          结合关键词排序
        </label>
        <div className="button-row">
          <button className="primary" value="search" disabled={!!busy}>
            {busy === "search" ? "本地检索中…" : "按含义搜索"}
          </button>
          {capabilities.data?.modules.llm?.enabled && (
            <button value="ask" disabled={!!busy}>
              {busy === "ask" ? "正在核对来源…" : "依据证据回答"}
            </button>
          )}
        </div>
      </form>
      {(error || status.error) && (
        <p className="error-box" role="alert">
          {error || "无法读取索引状态"}
        </p>
      )}
      {answer && (
        <div className="semantic-answer">
          <h3>
            {answer.supported ? "找到的原文证据" : "现有证据不足，无法确定。"}
          </h3>
          {answer.citations.map(cite)}
        </div>
      )}
      {hits && (
        <div className="semantic-hits">
          {!hits.length && <p>暂无可访问的匹配证据，请检查索引和会话许可。</p>}
          {hits.map((hit, i) => (
            <div key={hit.citation.message_id}>
              {cite(hit.citation, i)}
              <p className="fine">
                相似度 {hit.similarity.toFixed(3)}，仅表示语义接近程度。
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
