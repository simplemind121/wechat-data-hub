import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, type Entity, statusText } from "./api";

function Lookup({
  label,
  model,
  choose,
}: {
  label: string;
  model: string;
  choose: (id: number) => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<{ id: number; display_name: string }[]>(
    [],
  );
  const [error, setError] = useState("");
  return (
    <label>
      {label}
      <div className="button-row">
        <input
          aria-label={`${label}搜索`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          maxLength={100}
        />
        <button
          className="secondary"
          type="button"
          onClick={() => {
            setError("");
            void request<{ items: typeof items }>(
              `/integrations/odoo/lookup?model=${model}&q=${encodeURIComponent(q)}`,
            )
              .then((r) => setItems(r.items))
              .catch((e) =>
                setError(e instanceof Error ? e.message : "查询失败"),
              );
          }}
        >
          查询{label}
        </button>
      </div>
      <select
        aria-label={label}
        defaultValue=""
        onChange={(e) => choose(Number(e.target.value))}
      >
        <option value="" disabled>
          从测试实例查询后选择
        </option>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.display_name}
          </option>
        ))}
      </select>
      {error && <span role="alert">{error}</span>}
    </label>
  );
}

export function OdooDraft({ entity }: { entity: Entity }) {
  const targets: Record<string, string[]> = {
    quotation: ["purchase.order", "sale.order"],
    purchase_intent: ["purchase.order"],
    order_candidate: ["sale.order", "crm.lead"],
    customer: ["res.partner", "crm.lead"],
    supplier: ["res.partner"],
    product: ["product.template"],
  };
  const options = targets[entity.entity_type] || [];
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(options[0] || "");
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [linkExisting, setLinkExisting] = useState(true);
  const [preview, setPreview] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!options.length) return null;
  const data = {
    entity_id: entity.id,
    target_model: target,
    mapping: {
      ...mapping,
      existing_id: linkExisting ? mapping.existing_id : undefined,
    },
  };
  const labels: Record<string, string> = {
    "res.partner": "客户／供应商资料",
    "product.template": "产品资料",
    "purchase.order": "采购询价草稿",
    "sale.order": "销售报价草稿",
    "crm.lead": "销售线索",
  };
  function select(key: string, value: number) {
    setMapping({ ...mapping, [key]: value });
    setPreview(null);
    setConfirm(false);
  }
  return (
    <div>
      <button className="secondary" onClick={() => setOpen(!open)}>
        配置 Odoo 草稿投递
      </button>
      {open && (
        <section className="panel">
          <h3>核对后提交到测试实例</h3>
          <p className="fine">
            先在设置中验证 Odoo 连接，并安装 wdh_bridge
            模块。提交前核对现有客户、产品及草稿数量；最小起订量不会自动当作订单数量。
          </p>
          <label>
            目标操作
            <select
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                setPreview(null);
                setConfirm(false);
              }}
            >
              {options.map((model) => (
                <option key={model} value={model}>
                  {labels[model]}
                </option>
              ))}
            </select>
          </label>
          {["res.partner", "product.template"].includes(target) && (
            <>
              <label>
                资料处理方式
                <select
                  value={linkExisting ? "link" : "create"}
                  onChange={(e) => {
                    setLinkExisting(e.target.value === "link");
                    setPreview(null);
                    setConfirm(false);
                  }}
                >
                  <option value="link">关联已有资料</option>
                  <option value="create">核对后新建资料</option>
                </select>
              </label>
              {linkExisting && (
                <Lookup
                  label="已有资料"
                  model={target}
                  choose={(id) => select("existing_id", id)}
                />
              )}
            </>
          )}
          {["purchase.order", "sale.order"].includes(target) && (
            <div className="connector-grid">
              <Lookup
                label="客户或供应商"
                model="res.partner"
                choose={(id) => select("partner_id", id)}
              />
              <Lookup
                label="产品"
                model="product.product"
                choose={(id) => select("product_id", id)}
              />
              <Lookup
                label="币种"
                model="res.currency"
                choose={(id) => select("currency_id", id)}
              />
              <Lookup
                label="计量单位"
                model="uom.uom"
                choose={(id) => select("uom_id", id)}
              />
              <label>
                本次草稿数量
                <input
                  type="number"
                  min="0.000001"
                  step="any"
                  value={mapping.quantity || ""}
                  onChange={(e) => select("quantity", Number(e.target.value))}
                />
              </label>
            </div>
          )}
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              if (
                ["res.partner", "product.template"].includes(target) &&
                linkExisting &&
                !mapping.existing_id
              ) {
                setError("请先查询并选择要关联的已有资料。");
                return;
              }
              setBusy(true);
              setError("");
              void request("/integrations/odoo/plan", {
                method: "POST",
                body: JSON.stringify(data),
              })
                .then(setPreview)
                .catch((e) =>
                  setError(e instanceof Error ? e.message : "预览失败"),
                )
                .finally(() => setBusy(false));
            }}
          >
            核对投递预览
          </button>
          {preview !== null && (
            <>
              <p>
                目标：{labels[target]}
                。请核对上方选择的资料、数量，以及原始业务字段。
              </p>
              <details>
                <summary>查看字段映射明细</summary>
                <pre>{JSON.stringify(preview, null, 2)}</pre>
              </details>
              <label>
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                />
                已核对来源和映射，批准执行上述关联或草稿操作
              </label>
              <button
                disabled={!confirm || busy || queued}
                className="primary"
                onClick={() => {
                  setBusy(true);
                  setError("");
                  void request("/integrations/odoo/sync", {
                    method: "POST",
                    body: JSON.stringify({ ...data, confirm: true }),
                  })
                    .then(() => {
                      setQueued(true);
                      setConfirm(false);
                    })
                    .catch((e) =>
                      setError(e instanceof Error ? e.message : "投递失败"),
                    )
                    .finally(() => setBusy(false));
                }}
              >
                批准并加入投递队列
              </button>
            </>
          )}
          {queued && (
            <p role="status">已加入持久投递队列，可在设置中查看回读结果。</p>
          )}
          {error && (
            <p className="error-box" role="alert">
              {error}
            </p>
          )}
        </section>
      )}
    </div>
  );
}

export function OdooOutbox() {
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["odoo-outbox"],
    queryFn: () =>
      request<{
        items: {
          id: string;
          target_model: string;
          status: string;
          failure_code: string | null;
          remote_id: number | null;
          read_back: unknown;
          attempts: number;
        }[];
      }>("/integrations/odoo/outbox"),
    refetchInterval: 5000,
  });
  return (
    <section className="panel">
      <h2>Odoo 投递记录</h2>
      <p>
        已批准的任务由后台处理；超时重试沿用同一请求编号，成功后读取远端记录核对。
      </p>
      {query.data?.items.map((item) => (
        <article key={item.id}>
          <p>
            {item.target_model} · {statusText(item.status)} · 尝试{" "}
            {item.attempts} 次{" "}
            {item.remote_id && `· 远端编号 ${item.remote_id}`}
          </p>
          {item.failure_code && <p className="fine">{item.failure_code}</p>}
          {[
            "failed_permanent",
            "failed_retryable",
            "dead_letter",
            "cancelled",
          ].includes(item.status) && (
            <button
              className="secondary"
              onClick={() => {
                void request(`/integrations/odoo/outbox/${item.id}/retry`, {
                  method: "POST",
                })
                  .then(() => query.refetch())
                  .catch((e) =>
                    setError(e instanceof Error ? e.message : "重试失败"),
                  );
              }}
            >
              核对配置后批准重试
            </button>
          )}
          {item.read_back !== null && (
            <pre>{JSON.stringify(item.read_back, null, 2)}</pre>
          )}
        </article>
      ))}
      {query.data?.items.length === 0 && <p className="fine">尚无投递任务。</p>}
      {(error || query.error) && (
        <p role="alert">{error || "无法读取投递记录"}</p>
      )}
    </section>
  );
}
