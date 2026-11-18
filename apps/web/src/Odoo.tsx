import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request } from "./api";

type Report = {
  server_version: string;
  edition: string;
  target_19_ce: boolean;
  remote_writes: false;
  models: {
    model: string;
    status: string;
    read: boolean;
    create_permission: boolean | null;
  }[];
};
export function OdooConnection() {
  const status = useQuery({
    queryKey: ["odoo-status"],
    queryFn: () =>
      request<{ enabled: boolean; configured: boolean }>(
        "/integrations/odoo/status",
      ),
  });
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section className="panel">
      <h2>Odoo 独立联调</h2>
      <p>
        连接状态：
        {status.data?.enabled && status.data?.configured
          ? "已配置，待验证"
          : "尚未配置测试实例"}
      </p>
      <p className="fine">
        管理员在本地环境配置测试地址、数据库、用户名和 API
        密钥后，可验证版本与模型权限。此检查只读；草稿写入和回读仍需单独验收。密钥不在网页提交或显示。
      </p>
      <button
        disabled={busy || !status.data?.enabled || !status.data?.configured}
        onClick={() => {
          setBusy(true);
          setError("");
          setReport(null);
          void request<Report>("/integrations/odoo/test", { method: "POST" })
            .then(setReport)
            .catch((e) =>
              setError(e instanceof Error ? e.message : "连接验证未完成"),
            )
            .finally(() => setBusy(false));
        }}
      >
        {busy ? "正在只读验证…" : "验证测试实例连接与权限"}
      </button>
      {(error || status.error) && (
        <p className="error-box" role="alert">
          {error || "无法读取连接配置状态"}
        </p>
      )}
      {report && (
        <div>
          <p>
            {report.server_version} · {report.edition} ·{" "}
            {report.target_19_ce
              ? "符合 19 CE 版本目标"
              : "版本或版本类型需核对"}
          </p>
          {report.models.map((model) => (
            <p key={model.model}>
              {model.model}：{model.status} · 创建权限{" "}
              {model.create_permission === null
                ? "未验证"
                : model.create_permission
                  ? "允许"
                  : "拒绝"}
            </p>
          ))}
          <p className="fine">本次没有执行远端写入。</p>
        </div>
      )}
    </section>
  );
}
