import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";

test.describe.serial("complete local product", () => {
  test("setup, real import worker, search, evidence, review and export", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "创建你的工作空间" }),
    ).toBeVisible();
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "创建工作空间" }).click();
    await expect(
      page.getByRole("heading", { name: "让每一条记录，都有来处。" }),
    ).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-empty.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "数据导入", exact: true }).click();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载合成示例" }).click();
    const file = await download;
    const path = await file.path();
    expect(path).toBeTruthy();
    await page.getByLabel("选择导出文件", { exact: true }).setInputFiles({
      name: file.suggestedFilename(),
      mimeType: "application/zip",
      buffer: await readFile(path!),
    });
    await page.getByRole("button", { name: "校验并开始导入" }).click();
    await expect(
      page.getByText("原件已归档，后台任务已排队。可在下方查看进度。"),
    ).toBeVisible();
    await expect(page.getByText("已完成", { exact: true })).toBeVisible({
      timeout: 30000,
    });
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-imports.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "校验并开始导入" }).click();
    await expect(page.getByText("这份原件已归档，未重复写入。")).toBeVisible();
    await page.getByRole("button", { name: "会话", exact: true }).click();
    await page.getByRole("button", { name: /合成·产品讨论/ }).click();
    await expect(page.getByText("收到", { exact: true })).toHaveCount(2);
    await expect(page.getByText("源文件缺失")).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-conversations.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "查看证据" }).first().click();
    await expect(
      page.getByRole("dialog", { name: "消息与来源证据" }),
    ).toBeVisible();
    await expect(page.getByText("原始记录 SHA-256")).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-evidence.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "关闭详情" }).click();
    await page.getByRole("button", { name: "私人会话", exact: false }).click();
    await expect(
      page.getByRole("button", { name: "业务处理已允许", exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "查看证据" }).first().click();
    await page
      .getByRole("button", { name: "提取报价候选", exact: true })
      .click();
    await expect(
      page.getByText("已生成本地规则候选，请到业务实体页审核。"),
    ).toBeVisible();
    await page.getByRole("button", { name: "关闭详情" }).click();
    const exported = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出当前会话" }).click();
    expect((await exported).suggestedFilename()).toBe("conversation.jsonl");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByLabel("搜索关键词").fill("Ｍ６２０ 报价");
    await page.getByRole("button", { name: "搜索记录", exact: true }).click();
    await expect(page.getByText(/合成示例：M620 Ultra/)).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-search.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: /审核队列/ }).click();
    await page.getByRole("button", { name: "复核并作出决定" }).click();
    await page
      .getByLabel("复核理由")
      .fill("确认合成样例的两条收到是独立发送。");
    await page.getByRole("button", { name: "保存审核决定" }).click();
    await expect(page.getByText("当前没有需要处理的项目")).toBeVisible();
    await page.getByRole("button", { name: "审计日志", exact: true }).click();
    await expect(page.getByText("review.reject")).toBeVisible();
    await page.getByRole("button", { name: "业务实体", exact: true }).click();
    await page.getByRole("button", { name: "编辑并审核" }).click();
    await page
      .getByLabel("审核理由", { exact: true })
      .fill("逐字段核对原始消息，保留明确报价。");
    await page.getByRole("button", { name: "保存业务审核" }).click();
    await expect(page.getByText("已批准", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Odoo 同步预览" }).click();
    await expect(
      page.getByRole("dialog", { name: "Odoo 本地同步预览" }),
    ).toBeVisible();
    await expect(
      page.getByText('"remote_writes": false', { exact: false }),
    ).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-odoo-preview.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "关闭详情" }).click();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page
      .getByLabel("备份口令", { exact: true })
      .fill("synthetic-browser-backup-passphrase");
    await page
      .getByLabel("再次输入口令", { exact: true })
      .fill("synthetic-browser-backup-passphrase");
    const encrypted = page.waitForEvent("download");
    await page.getByRole("button", { name: "生成并下载加密备份" }).click();
    expect((await encrypted).suggestedFilename()).toBe(
      "wechat-data-hub.wdhbak",
    );
    await expect(
      page.getByText("加密备份已下载。口令不会保存在服务器配置中。"),
    ).toBeVisible();
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  });

  test("existing user login and mobile usable layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await expect(
      page.getByRole("heading", { name: "让每一条记录，都有来处。" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(390);
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/product-mobile.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "会话", exact: true }).click();
    await page.getByRole("button", { name: /合成·产品讨论/ }).click();
    await expect(page.getByText("收到", { exact: true })).toHaveCount(2);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(390);
  });

  test("available image attachment is preserved and can be previewed", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await page.getByRole("button", { name: "数据导入", exact: true }).click();
    const data = execFileSync(
      ".venv/bin/python",
      [
        "-c",
        "from tests.integration.test_formats import media_bundle; import sys; sys.stdout.buffer.write(media_bundle()[0])",
      ],
      { cwd: "../.." },
    );
    await page.getByLabel("选择导出文件", { exact: true }).setInputFiles({
      name: "media-demo.zip",
      mimeType: "application/zip",
      buffer: data,
    });
    await page.getByRole("button", { name: "校验并开始导入" }).click();
    await expect(page.getByText("已完成", { exact: true })).toHaveCount(2, {
      timeout: 30000,
    });
    await page.getByRole("button", { name: "会话", exact: true }).click();
    await page.getByRole("button", { name: /合成·产品讨论/ }).click();
    await page.getByRole("button", { name: "预览", exact: true }).click();
    const image = page.getByRole("img", { name: "pixel.png" });
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth))
      .toBe(1);
  });

  test("local Chinese OCR, coordinates, evidence export and derived search", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page
      .getByRole("button", { name: "启用图片文字识别", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "关闭图片文字识别", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "数据导入", exact: true }).click();
    const data = execFileSync(
      ".venv/bin/python",
      [
        "-c",
        "from tests.integration.test_processing import processing_image_bundle; import sys; sys.stdout.buffer.write(processing_image_bundle()[0])",
      ],
      { cwd: "../.." },
    );
    await page.getByLabel("选择导出文件", { exact: true }).setInputFiles({
      name: "synthetic-ocr.zip",
      mimeType: "application/zip",
      buffer: data,
    });
    await page.getByRole("button", { name: "校验并开始导入" }).click();
    await expect(
      page.getByText("原件已归档，后台任务已排队。可在下方查看进度。"),
    ).toBeVisible();
    await page.getByRole("button", { name: "会话", exact: true }).click();
    await page.getByRole("button", { name: /合成·产品讨论/ }).click();
    const card = page
      .locator("article.message-card")
      .filter({ hasText: "仅合成图片，文字需从图中识别" });
    await expect(card).toBeVisible({ timeout: 30000 });
    await card.getByRole("button", { name: "查看证据" }).click();
    await page
      .getByRole("button", { name: "识别图片文字", exact: true })
      .click();
    await expect(
      page.getByText("图片文字识别 · 已完成", { exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".recognized-text")).toContainText("3200");
    await expect(page.locator(".recognized-text")).toContainText("报价");
    await page
      .getByRole("button", { name: "定位原图文字", exact: true })
      .click();
    await expect(
      page.getByRole("img", { name: "OCR原图与文字位置" }),
    ).toBeVisible();
    await expect(page.locator("rect.ocr-selected-box")).toHaveCount(1);
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/ocr-coordinates.png",
        fullPage: true,
      });
    const evidence = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "导出识别证据", exact: true })
      .click();
    expect((await evidence).suggestedFilename()).toBe(
      "recognition-evidence.json",
    );
    await page.getByRole("button", { name: "关闭详情" }).click();
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByLabel("搜索关键词").fill("3200");
    await page.getByRole("button", { name: "搜索记录", exact: true }).click();
    await expect(
      page.getByText("仅合成图片，文字需从图中识别", { exact: true }),
    ).toBeVisible();
  });

  test("local voice transcription preserves source and supports timed playback", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page
      .getByRole("button", { name: "启用语音转文字", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "关闭语音转文字", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "数据导入", exact: true }).click();
    const data = execFileSync(
      ".venv/bin/python",
      [
        "-c",
        "from tests.integration.test_asr import audio_bundle; import sys; sys.stdout.buffer.write(audio_bundle()[0])",
      ],
      { cwd: "../.." },
    );
    await page.getByLabel("选择导出文件", { exact: true }).setInputFiles({
      name: "synthetic-voice.zip",
      mimeType: "application/zip",
      buffer: data,
    });
    await page.getByRole("button", { name: "校验并开始导入" }).click();
    await expect(
      page.getByText("原件已归档，后台任务已排队。可在下方查看进度。"),
    ).toBeVisible();
    await page.getByRole("button", { name: "会话", exact: true }).click();
    await page.getByRole("button", { name: /合成·产品讨论/ }).click();
    const card = page
      .locator("article.message-card")
      .filter({ hasText: "合成语音测试，转录需核对原音频" });
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.getByRole("button", { name: "查看证据" }).click();
    await page.getByRole("button", { name: "转录语音", exact: true }).click();
    await expect(
      page.getByText("语音转文字 · 已完成", { exact: true }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".recognized-text")).toContainText("synthetic");
    await page
      .getByRole("button", { name: "核对原始语音", exact: true })
      .click();
    await expect(page.getByLabel("原始语音", { exact: true })).toBeVisible();
    await expect(page.locator(".transcript-segment").first()).toContainText(
      "synthetic",
    );
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/asr-timestamps.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "关闭详情" }).click();
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByLabel("搜索关键词").fill("synthetic recording");
    await page.getByRole("button", { name: "搜索记录", exact: true }).click();
    await expect(
      page.getByText("合成语音测试，转录需核对原音频", { exact: true }),
    ).toBeVisible();
  });
  test("local semantic search, cited answers and pending AI candidates", async ({
    page,
  }) => {
    test.setTimeout(90000);
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await page
      .getByRole("button", { name: "启用语义检索", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "关闭语义检索", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "启用AI 摘要与候选", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "关闭AI 摘要与候选", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page
      .getByRole("button", { name: "索引业务会话消息", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("已排队");
    await expect(page.getByText(/已索引 [1-9].*待处理 0 项/)).toBeVisible({
      timeout: 30000,
    });
    await page.getByLabel("语义问题").fill("M620的价格是多少");
    await page.getByRole("button", { name: "按含义搜索", exact: true }).click();
    await expect(page.locator(".semantic-hits")).toContainText("3200", {
      timeout: 15000,
    });
    await page
      .getByRole("button", { name: "依据证据回答", exact: true })
      .click();
    await expect(page.locator(".semantic-answer")).toContainText("3200", {
      timeout: 30000,
    });
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/semantic-cited-answer.png",
        fullPage: true,
      });
    await page
      .getByRole("button", { name: "查看引用 1 的原消息", exact: true })
      .click();
    await page
      .getByRole("button", { name: "AI 摘要与提取候选", exact: true })
      .first()
      .click();
    await expect(
      page.getByText("AI 摘要与候选 · 已完成", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
    await expect(page.getByText(/已生成 [1-9].*个待审核候选/)).toBeVisible();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/ai-source-candidates.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "关闭详情" }).click();
    await page.getByLabel("语义问题").fill("2029年火星基地的租金是多少");
    await page
      .getByRole("button", { name: "依据证据回答", exact: true })
      .click();
    await expect(page.locator(".semantic-answer")).toContainText(
      "现有证据不足，无法确定。",
      { timeout: 15000 },
    );
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  });
  test("collector setup, durable upload, pause and mobile controls", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByLabel("用户名", { exact: true }).fill("browser-owner");
    await page
      .getByLabel("密码", { exact: true })
      .fill("synthetic-browser-password");
    await page.getByRole("button", { name: "登录工作空间" }).click();
    await page.getByRole("button", { name: "数据导入", exact: true }).click();
    await page.getByLabel("数据源名称", { exact: true }).fill("合成同步端");
    await page
      .getByLabel("微信账号别名", { exact: true })
      .fill("collector-browser");
    await page
      .getByLabel("来源设备标识", { exact: true })
      .fill("collector-browser-device");
    await page.getByRole("button", { name: "创建数据源", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "采集端配置仅本次可下载" }),
    ).toBeVisible();
    const downloading = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "下载采集端配置", exact: true })
      .click();
    const downloaded = await downloading;
    const config = JSON.parse(
      await readFile((await downloaded.path())!, "utf8"),
    );
    expect(config.token).toMatch(/^wdhc_/);
    await page.getByRole("button", { name: "已保存，关闭" }).click();
    const raw = Buffer.from(
      JSON.stringify({
        conversation_ref: "合成同步会话",
        sender_ref: "fixture",
        sent_at: "2026-11-20T08:00:00+08:00",
        message_type: "text",
        body_text: "连接器验收 😀",
      }) + "\n",
    );
    const headers = { Authorization: `Bearer ${config.token}` };
    const first = await page.request.post("/api/v1/collector/batches", {
      headers,
      multipart: {
        cursor: "browser-fixture-1",
        file: {
          name: "messages.jsonl",
          mimeType: "application/octet-stream",
          buffer: raw,
        },
      },
    });
    expect(first.status()).toBe(202);
    const result = await first.json();
    const again = await page.request.post("/api/v1/collector/batches", {
      headers,
      multipart: {
        cursor: "browser-fixture-1",
        file: {
          name: "messages.jsonl",
          mimeType: "application/octet-stream",
          buffer: raw,
        },
      },
    });
    expect((await again.json()).import_id).toBe(result.import_id);
    await expect
      .poll(
        async () =>
          (
            await (
              await page.request.get(`/api/v1/jobs/${result.job_id}`)
            ).json()
          ).status,
      )
      .toBe("completed");
    const card = page
      .locator("article")
      .filter({
        has: page.getByRole("heading", {
          name: "合成同步端 · 个人微信文件",
          exact: true,
        }),
      });
    await card.getByRole("button", { name: "暂停同步", exact: true }).click();
    await expect(
      card.getByRole("button", { name: "恢复同步", exact: true }),
    ).toBeVisible();
    expect(
      (
        await page.request.get("/api/v1/collector/status", { headers })
      ).status(),
    ).toBe(401);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    if (process.env.WDH_CAPTURE_SCREENSHOTS)
      await page.screenshot({
        path: "../../docs/evidence/connectors04-source-mobile.png",
        fullPage: true,
      });
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Odoo 投递记录", exact: true }),
    ).toBeVisible();
  });
});
