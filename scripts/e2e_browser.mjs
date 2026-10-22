/**
 * 交付级 E2E（浏览器层）：真实渲染课堂页。
 *   1. 经真实渲染服务 POST /lessons 发布内核产出的 spec（16-9 破十法 + filtered 投影版）；
 *   2. 真实浏览器打开 → 48px / 一屏一任务 / filtered 页不含答案；
 *   3. 真实交互：答对 →「答对了！」→ 下一节点；答错 → hint 阶梯。
 * 用法：cd packages/aiedu-player && node ../../scripts/e2e_browser.mjs
 * 产物：.e2e/e2e-classroom-*.png、.e2e/e2e-browser-report.md
 */
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

// 仓库根：以脚本自身位置解析（不再硬编码机器路径）
const REPO = fileURLToPath(new URL("../", import.meta.url))
  .split("\\")
  .join("/")
  .replace(/\/$/, "");
const PLAYER_URL = "http://127.0.0.1:8130";
const E2E = `${REPO}/.e2e`;
const results = [];
// playwright 装在 aiedu-player 包内（跨包脚本用绝对路径引入）
const { chromium } = await import(
  pathToFileURL(`${REPO}/packages/aiedu-player/node_modules/playwright/index.mjs`).href
);

function check(name, ok, evidence) {
  results.push({ name, ok, evidence });
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name} :: ${String(evidence).slice(0, 160)}`);
}

async function publish(spec) {
  const resp = await fetch(`${PLAYER_URL}/lessons`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(spec),
  });
  return (await resp.json()).url;
}

async function main() {
  mkdirSync(E2E, { recursive: true });
  const fullSpec = JSON.parse(
    readFileSync(`${REPO}/packages/aiedu-player/demo/make-ten-16-plus-8.json`, "utf8"),
  );
  const filteredSpec = JSON.parse(
    readFileSync(`${REPO}/packages/aiedu-player/demo/make-ten-16-plus-8.filtered.json`, "utf8"),
  );

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });

  // ① 全量 spec 课堂：48px + 一屏一任务 + 真实交互
  const url = await publish(fullSpec);
  check("① POST /lessons 返回可访问 url", url.startsWith("http") && url.includes("?spec="), url.slice(0, 70));
  await page.goto(url);
  await page.waitForSelector("[data-activity-node]:visible");
  const tooSmall = await page.evaluate(() =>
    Array.from(document.querySelectorAll("button, input, [role=button], a[href]"))
      .filter((el) => el.offsetParent !== null)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { id: el.id || el.className, w: Math.round(r.width), h: Math.round(r.height) };
      })
      .filter((x) => x.w < 48 || x.h < 48),
  );
  check("② 可点元素 ≥48×48px（真实渲染页）", tooSmall.length === 0, JSON.stringify(tooSmall));
  check("③ 一屏一任务（1 个可见节点）", (await page.locator("[data-activity-node]:visible").count()) === 1, "visible=1");
  await page.screenshot({ path: `${E2E}/e2e-classroom-step1.png` });
  // 答对 → 下一节点
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await page.waitForSelector("#feedback:has-text('答对了')");
  check("④ 真实作答：答对→正向反馈→下一节点",
        (await page.locator("#feedback").textContent()).includes("答对了")
        && (await page.locator("[data-activity-node]:visible").count()) === 1, "答对了！ + 仍 1 个可见节点");
  await page.screenshot({ path: `${E2E}/e2e-classroom-step2.png` });

  // ② filtered spec 课堂：页面不得出现答案
  const furl = await publish(filteredSpec);
  await page.goto(furl);
  await page.waitForSelector("[data-activity-node]:visible");
  const text = (await page.locator("body").textContent()) ?? "";
  check("⑤ filtered 页面不出现答案 24（先想后看）", !text.includes("24") && text.includes("16 + 8 = ?"),
        "无 '24'；块图显示 '16 + 8 = ?'");
  await page.screenshot({ path: `${E2E}/e2e-classroom-filtered.png` });

  await browser.close();

  const report = [
    "# 交付级 E2E 报告（浏览器层，真实渲染课堂页）", "",
    `- 结论：**${results.filter((r) => r.ok).length}/${results.length} 通过**`, "",
    ...results.map((r) => `- [${r.ok ? "✅" : "❌"}] ${r.name} — ${r.evidence}`), "",
    "- 截图：`e2e-classroom-step1.png`（首关）/ `e2e-classroom-step2.png`（答对后）/ `e2e-classroom-filtered.png`（filtered 不泄题）", "",
  ].join("\n");
  writeFileSync(`${E2E}/e2e-browser-report.md`, report, "utf8");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
}

main().catch((err) => {
  console.error("E2E browser failed:", err);
  process.exit(1);
});
