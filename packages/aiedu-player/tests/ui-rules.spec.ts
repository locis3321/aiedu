import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * 硬约束 5（儿童界面可用性）断言：基于真实渲染服务页面（不是静态 fixture）。
 * - 可点元素 ≥48×48px（单指可操作）；
 * - 一屏一任务：同一时刻只有一个 activity 节点可见；
 * - filtered（投影后）页面不出现答案文本（答案门控只在投影层）。
 */

const PLAYER = "http://127.0.0.1:8130";
const DEMO = new URL("../demo/", import.meta.url);

function loadSpec(name: string): unknown {
  return JSON.parse(readFileSync(new URL(name, DEMO), "utf8"));
}

async function publish(spec: unknown): Promise<string> {
  const resp = await fetch(`${PLAYER}/lessons`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(spec),
  });
  expect(resp.ok, "渲染服务应接受合法 LessonSpec v2").toBeTruthy();
  const payload = (await resp.json()) as { url: string };
  return payload.url;
}

test("渲染服务：POST /lessons 返回可访问 url 且页面渲染成功", async ({ page }) => {
  const url = await publish(loadSpec("make-ten-16-plus-8.json"));
  expect(url).toContain("/lesson.html?spec=");
  await page.goto(url);
  await expect(page.locator("[data-activity-node]:visible")).toHaveCount(1);
});

test("硬约束5：真实渲染页可点元素 ≥48×48px", async ({ page }) => {
  const url = await publish(loadSpec("make-ten-16-plus-8.json"));
  await page.goto(url);
  await expect(page.locator("[data-activity-node]:visible")).toHaveCount(1);
  const tooSmall = await page.evaluate(() => {
    const selector = 'button, input, [role="button"], a[href]';
    return Array.from(document.querySelectorAll<HTMLElement>(selector))
      .filter((el) => el.offsetParent !== null) // 仅可见元素
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return { id: el.id || el.className, w: Math.round(rect.width), h: Math.round(rect.height) };
      })
      .filter((x) => x.w < 48 || x.h < 48);
  });
  expect(tooSmall, "可点元素必须 ≥48px（单指可操作）").toEqual([]);
});

test("硬约束5：一屏一任务（同一时刻仅一个 activity 节点可见）", async ({ page }) => {
  const url = await publish(loadSpec("make-ten-16-plus-8.json"));
  await page.goto(url);
  await expect(page.locator("[data-activity-node]:visible")).toHaveCount(1);
  // 答对后进入下一节点：仍然只有一个可见节点
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
  await expect(page.locator("[data-activity-node]:visible")).toHaveCount(1);
});

test("答案门控：filtered（投影后）页面不出现答案", async ({ page }) => {
  const url = await publish(loadSpec("make-ten-16-plus-8.filtered.json"));
  await page.goto(url);
  await expect(page.locator("[data-activity-node]:visible")).toHaveCount(1);
  const text = (await page.locator("body").textContent()) ?? "";
  // 24 = 16+8 的答案（由内核投影清空 expected/claims/narration）
  expect(text).not.toContain("24");
  expect(text).toContain("16 + 8 = ?"); // 块图不自行计算答案
});


test("无答案预览（C4）：横幅存在 + 免判定推进到末节点 + 48px 不回退", async ({ page }) => {
  const url = await publish(loadSpec("make-ten-16-plus-8.filtered.json"));
  await page.goto(url);
  await expect(page.locator("#preview-banner")).toBeVisible();
  await expect(page.locator("#preview-banner")).toContainText("不含答案");
  // 免判定推进：逐节点点击"记下答案，继续"，直到完成（末节点后 session completed）
  let steps = 0;
  for (let i = 0; i < 10; i++) {
    await page.click("#submit-btn");
    steps += 1;
    const fb = (await page.locator("#feedback").textContent()) ?? "";
    if (fb.includes("已记录（未经判定）")) {
      await expect(page.locator("#submit-btn")).toHaveText(/记下答案/);
    }
    const status = (await page.locator("#status").textContent()) ?? "";
    if (status.includes("completed")) break;
  }
  expect(steps).toBeLessThan(10); // 5 节点内完成
  // 48px 断言不回退
  const tooSmall = await page.evaluate(() => {
    const selector = 'button, input, [role="button"], a[href]';
    return Array.from(document.querySelectorAll<HTMLElement>(selector))
      .filter((el) => el.offsetParent !== null)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { id: el.id || el.className, w: Math.round(r.width), h: Math.round(r.height) };
      })
      .filter((x) => x.w < 48 || x.h < 48);
  });
  expect(tooSmall).toEqual([]);
});
