export type Page<T> = { items: T[]; next_cursor: string | null };
export type Me = {
  user: { id: string; username: string };
  role: "admin" | "reviewer" | "reader";
  workspace_id: string;
  workspace_name?: string;
  csrf_token: string;
};
export type Attachment = {
  id: string;
  original_filename: string;
  availability: string;
  mime_type: string;
  byte_size: number | null;
  sha256: string | null;
  source_path: string;
};
export type Message = {
  id: string;
  conversation_id: string;
  sender: string;
  body_text: string | null;
  sent_at: string | null;
  message_type: string;
  observation_count: number;
  merge_status: string;
  original_time_text: string | null;
  reply_source_ref: string | null;
  reply_to_id: string | null;
  attachments: Attachment[];
  observations?: Observation[];
  privacy_scope?: string;
  processing_results?: ProcessingResult[];
};
export type ProcessingResult = {
  id: string;
  kind: string;
  job_id: string;
  message_id: string;
  attachment_id: string | null;
  source_sha256: string;
  provider_version: string;
  text: string;
  search_text: string;
  status?: string;
  failure_code?: string | null;
  details: {
    segments?: { start: number; end: number; text: string }[];
    duration_seconds?: number;
    timestamp_granularity?: string;
    languages?: string[];
    width?: number;
    height?: number;
    words?: {
      text: string;
      bbox: [number, number, number, number];
      confidence_raw: number;
    }[];
    entity_ids?: string[];
    rejected_candidates?: { kind: string; reason: string }[];
    source_result_id?: string | null;
    dimensions?: number;
  };
};
export type ProcessingCapabilities = {
  modules: Record<
    string,
    {
      enabled: boolean;
      available: boolean;
      reason: string | null;
      provider_version: string;
      installable?: boolean;
      download_bytes?: number;
      install_job?: {
        id: string;
        status: string;
        failure_code: string | null;
      } | null;
    }
  >;
  external_inference: boolean;
  model_download_requires_network: boolean;
};
export type Entity = {
  id: string;
  entity_type: string;
  extractor_version: string;
  payload: Record<string, string>;
  evidence: { field: string; message_id: string; source_span: string }[];
  review_status: string;
  approved_payload: Record<string, string> | null;
};
export type Observation = {
  id: string;
  source_message_id: string | null;
  device: { device_ref: string; platform: string; wechat_version: string };
  batch: {
    id: string;
    sha256: string;
    adapter_id: string;
    adapter_version: string;
  };
  raw: {
    id: string;
    source_record_locator: string;
    raw_sha256: string;
    raw_payload: unknown;
  };
  observed_fields: unknown;
};
export type Conversation = {
  id: string;
  title: string;
  native_ref: string;
  message_count: number;
  preview: string;
  privacy_scope: string;
  kind: string;
};
export type Job = {
  id: string;
  status: string;
  attempt_count: number;
  failure_code: string | null;
};
export type Batch = {
  id: string;
  batch_status: string;
  created_at: string;
  source: {
    device_ref: string;
    platform: string;
    exporter_name: string;
    exported_at: string;
  };
  job: Job | null;
  progress: { processed: number; normalized: number; quarantined: number };
};
export type Review = {
  id: string;
  review_type: string;
  status: string;
  messages: Message[];
  contacts: { id: string; display_name: string; native_ref: string }[];
  decision: { action: string; reason: string } | null;
};
export type Overview = {
  messages: number;
  conversations: number;
  attachments: number;
  devices: number;
  pending_reviews: number;
  imports: number;
  running_jobs: number;
  accounts: { id: string; account_ref: string }[];
  sources: { id: string; device_ref: string }[];
  features: Record<string, boolean>;
};
export type Audit = {
  id: string;
  event_type: string;
  actor_id: string | null;
  created_at: string;
  result: string;
  object_id: string | null;
  details: Record<string, unknown>;
};

let csrf = "";
export function setCsrf(token: string) {
  csrf = token;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as {
      message?: string;
      code?: string;
    };
    throw new Error(error.message || `服务返回错误 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function download(path: string, filename: string, body?: unknown) {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    method: body ? "POST" : "GET",
    body: body ? JSON.stringify(body) : undefined,
    headers: {
      "X-CSRF-Token": csrf,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok)
    throw new Error(
      ((await response.json()) as { message?: string }).message || "下载失败",
    );
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export const statusName: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  completed: "已完成",
  archived: "已归档",
  normalizing: "正在规范化",
  review_required: "有待复核项",
  failed_retryable: "等待重试",
  failed_permanent: "文件处理失败",
  dead_letter: "重试次数已用尽",
  cancelled: "已取消",
  single_source: "单一来源",
  verified: "已确认",
  candidate: "待复核",
  conflicted: "来源有差异",
  missing: "源文件缺失",
  available: "可用",
};
export const statusText = (status: string) => statusName[status] || status;
export const dateText = (date: string | null) =>
  date
    ? new Date(
        date.endsWith("Z") || /[+-]\d\d:\d\d$/.test(date) ? date : date + "Z",
      ).toLocaleString("zh-CN", { hour12: false })
    : "时间未确认";

export async function attachmentBlob(id: string): Promise<Blob> {
  const response = await fetch(`/api/v1/attachments/${id}/download`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new Error("附件无法读取，请检查来源文件和权限");
  return response.blob();
}
