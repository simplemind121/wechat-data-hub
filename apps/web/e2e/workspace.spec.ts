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
    await page
      .getByLabel("选择导出文件", { exact: true })
      .setInputFiles({
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
    await page
      .getByLabel("选择导出文件", { exact: true })
      .setInputFiles({
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
});
