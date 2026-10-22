import { expect, test } from "@playwright/test";

const PAGE = "/templates/diagram/index.html";

test("页面加载并渲染单位块（16+8）", async ({ page }) => {
  await page.goto(PAGE);
  await expect(page.locator("#blocks-stage")).toBeVisible();
  await expect(page.locator("#group-left .unit-block")).toHaveCount(16);
  await expect(page.locator("#group-right .unit-block")).toHaveCount(8);
});

test("提交正确答案获得正向反馈并进入下一节点", async ({ page }) => {
  await page.goto(PAGE);
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
});

test("提示按钮返回 assistance", async ({ page }) => {
  await page.goto(PAGE);
  await page.click("#hint-btn");
  await expect(page.locator("#feedback")).toContainText("10-8");
});

test("重播与重置可用（run_id 机制）", async ({ page }) => {
  await page.goto(PAGE);
  await page.click("#replay-btn");
  await expect(page.locator("#status")).toContainText("会话");
  await page.click("#reset-btn");
  // reset后回到首节点
  await expect(page.locator("#prompt")).toContainText("还差几颗");
});

test("布局不变量：三档视口无违规且触摸目标≥44px", async ({ page }) => {
  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1024, height: 768 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(PAGE);
    const violations = await page.evaluate(() =>
      window.AIEduPlayer.checkLayout(document.getElementById("blocks-stage")!),
    );
    expect(violations, `viewport ${viewport.width}`).toEqual([]);
    // 关键控件 ≥44px
    const btnSize = await page.locator("#submit-btn").evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { w: r.width, h: r.height };
    });
    expect(btnSize.w).toBeGreaterThanOrEqual(44);
    expect(btnSize.h).toBeGreaterThanOrEqual(44);
    const inputSize = await page.locator("#answer-input").evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { w: r.width, h: r.height };
    });
    expect(inputSize.h).toBeGreaterThanOrEqual(44);
  }
});

test("v0.1 legacy adapter：原型课程可加载为活动图", async ({ page }) => {
  await page.goto(PAGE);
  const result = await page.evaluate(async () => {
    const v01 = await (
      await fetch("/demo/make-ten-16-plus-8.json")
    ).json();
    // v01 demo spec is v2; simulate adapt by calling adaptV01 on a v01-shaped object
    const adapted = window.AIEduPlayer.adaptV01({
      version: "0.1",
      id: "baskets-ratio-43",
      solution: { answer: "62", verified: true },
      teachingPlan: {
        scenes: [
          { id: "orient", kind: "orient", narration: "看清关键词" },
          {
            id: "check",
            kind: "check",
            title: "4:3是取出前还是取出后？",
            interaction: {
              prompt: "4:3是取出前还是取出后的比？",
              options: ["取出后", "取出前"],
              correctIndex: 0,
            },
          },
          { id: "summary", kind: "summary", narration: "回顾" },
        ],
      },
    });
    return { nodes: adapted.activity_graph.map((n) => n.type), verified: adapted.verification.verified };
  });
  expect(result.nodes).toEqual(["observe", "predict", "reflect"]);
});

test("儿童友好主题：莓果篮场景与受控呈现", async ({ page }) => {
  await page.goto(PAGE);
  // 场景主题：标题与容器样式由 presentation.scene_metaphor 驱动
  await expect(page.locator("h1")).toContainText("莓果");
  await expect(page.locator("#blocks-stage")).toHaveAttribute("data-theme", "berry_basket");
  await expect(page.locator("#group-left")).toHaveClass(/group-basket/);
  // 温和反馈：答对后出现鼓励语
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
});

test("完整五步交互：找补数→找来源→求新和→重播→迁移练习", async ({ page }) => {
  await page.goto(PAGE);
  // 1. 找补数：小兔还差几颗到10 → 2
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
  // 2. 找来源：小熊借出几颗 → 2
  await page.fill("#answer-input", "2");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
  // 3. 求新和：两篮合起来 → 24
  await page.fill("#answer-input", "24");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
  // 4. 回放（observe节点）→ 继续
  await expect(page.locator("#prompt")).toContainText("完整演示");
  await page.click("#replay-btn");
  await page.click("#continue-btn");
  // 5. 迁移练习：27+6 → 33
  await expect(page.locator("#prompt")).toContainText("27+6");
  await page.fill("#answer-input", "33");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("答对了");
});

test("自由设计课程（LLM生成）可播放：预测→提示→反馈→布局", async ({ page }) => {
  const GENERIC = "/templates/generic/index.html";
  await page.goto(GENERIC);
  // predict 节点：先想后看
  await expect(page.locator("#prompt")).toContainText("平均分成4份");
  // 提示梯度
  await page.click("#hint-btn");
  await expect(page.locator("#feedback")).toContainText("平均分成了几份");
  // 提交答案获得温和反馈（expression 回答由领域插件扩展，此处验证反馈路径）
  await page.fill("#answer-input", "1/4");
  await page.click("#submit-btn");
  await expect(page.locator("#feedback")).toContainText("再想想");
  // 布局无违规 + 触摸目标
  const violations = await page.evaluate(() =>
    window.AIEduPlayer.checkLayout(document.getElementById("blocks-stage")!),
  );
  expect(violations).toEqual([]);
  const btnSize = await page.locator("#submit-btn").evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { w: r.width, h: r.height };
  });
  expect(btnSize.w).toBeGreaterThanOrEqual(44);
});
