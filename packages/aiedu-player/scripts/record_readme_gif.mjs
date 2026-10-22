/**
 * 录制 README 首屏 GIF（真实操作，非拼贴）：
 *   1. 起真实 aiedu-mcp（stdio）与真实渲染服务（aiedu-player）；
 *   2. 浏览器里展示真实接入配置 + 真实 MCP 调用返回（逐条实时注入）；
 *   3. 打开真实渲染课堂页并真实作答（答对→反馈→下一节点）；
 *   4. Playwright 录成 webm → ffmpeg 解帧 → Pillow 合成 GIF。
 *
 * 用法：cd packages/aiedu-player && node scripts/record_readme_gif.mjs
 * 产物：docs/assets/readme-demo.gif（+ 临时帧目录，最后清理）
 */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, existsSync } from "node:fs";
import { createInterface } from "node:readline";
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../../", import.meta.url))
  .split("\\")
  .join("/")
  .replace(/\/$/, "");
const PY = `${ROOT}/packages/aiedu-mcp/.venv/Scripts/python.exe`;
const OUT_DIR = `${ROOT}/docs/assets`;
const FRAMES = `${ROOT}/.gif-frames`;
const VIDEO_DIR = `${ROOT}/.gif-video`;
const MCP_PORT = 8124;
const PLAYER_PORT = 8130;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 极简 MCP stdio 客户端：换行分隔 JSON-RPC。 */
class McpStdio {
  constructor(cmd, args) {
    this.proc = spawn(cmd, args, { cwd: `${ROOT}/packages/aiedu-mcp` });
    this.rl = createInterface({ input: this.proc.stdout });
    this.pending = new Map();
    this.id = 0;
    this.rl.on("line", (line) => {
      if (!line.trim()) return;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        return;
      }
      const resolver = this.pending.get(msg.id);
      if (resolver) {
        this.pending.delete(msg.id);
        resolver(msg);
      }
    });
  }

  send(method, params) {
    const id = ++this.id;
    const payload = { jsonrpc: "2.0", id, method, params };
    this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
    return new Promise((resolve, reject) => {
      this.pending.set(id, resolve);
      setTimeout(() => reject(new Error(`timeout: ${method}`)), 60000);
    });
  }

  notify(method, params) {
    this.proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
  }

  close() {
    this.proc.kill();
  }
}

async function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  rmSync(FRAMES, { recursive: true, force: true });
  rmSync(VIDEO_DIR, { recursive: true, force: true });

  // 真实渲染服务
  const player = spawn("node", [`${ROOT}/packages/aiedu-player/server/serve.mjs`, String(PLAYER_PORT)], {
    cwd: `${ROOT}/packages/aiedu-player`,
  });
  await sleep(1500);

  // 真实 MCP server（stdio）
  const mcp = new McpStdio(PY, ["-m", "aiedu_mcp.server", "--transport", "stdio"]);
  const init = await mcp.send("initialize", {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "readme-recorder", version: "0.1.0" },
  });
  mcp.notify("notifications/initialized", {});
  console.log("[record] MCP server:", init.result.serverInfo);

  const call = async (name, args) => {
    const res = await mcp.send("tools/call", { name, arguments: args });
    if (res.result?.isError) throw new Error(`tool ${name} error`);
    return JSON.parse(res.result.content[0].text);
  };

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 900, height: 620 },
    recordVideo: { dir: VIDEO_DIR, size: { width: 900, height: 620 } },
  });
  const page = await context.newPage();

  const configJson = readFileSync(`${ROOT}/examples/claude_code_mcp.json`, "utf8");
  await page.setContent(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
  body{margin:0;background:#0f1115;color:#e6e6e6;font-family:"Cascadia Code",Consolas,"Microsoft YaHei",monospace;padding:18px 22px}
  h2{font-size:15px;color:#8ab4f8;margin:0 0 6px}
  .sub{font-size:12px;color:#8b949e;margin-bottom:12px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:10px 12px;margin-bottom:9px;opacity:0;transform:translateY(6px);transition:.35s}
  .card.show{opacity:1;transform:none}
  .k{color:#7ee787;font-size:13px}
  pre{white-space:pre-wrap;word-break:break-all;font-size:12px;color:#c9d1d9;margin:6px 0 0}
  .label{font-size:12px;color:#d2a8ff}
</style></head><body>
  <h2>数芽 · 数学可信教学引擎</h2>
  <div class="sub">给 AI Agent 的 MCP server：SymPy 级核验 + 教学门禁 + 答案门控渲染</div>
  <div class="card" id="cfg"><h2>① 接入（Claude Code / 任意 MCP 宿主）</h2><pre id="cfgjson"></pre></div>
  <div id="cards"></div>
</body></html>`);
  await page.evaluate((cfg) => {
    document.getElementById("cfgjson").textContent = cfg;
    document.getElementById("cfg").classList.add("show");
  }, configJson);
  await sleep(2600);

  const addCard = async (label, body) => {
    await page.evaluate(
      ([label, body]) => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `<div class="label">${label}</div><pre></pre>`;
        card.querySelector("pre").textContent = body;
        document.getElementById("cards").appendChild(card);
        requestAnimationFrame(() => card.classList.add("show"));
      },
      [label, body],
    );
    await sleep(2200);
  };

  // ② verify_math
  const vm = await call("verify_math", { expression: "7x8", expected: 56 });
  await addCard(
    "② verify_math('7x8', 56) — 数学对错由 SymPy 判定，不靠模型",
    JSON.stringify(vm, null, 2),
  );

  // ③ generate_lesson
  const gen = await call("generate_lesson", { question: "16-9" });
  await addCard(
    `③ generate_lesson('16-9') — 已核验的破十法课（lesson_id=${gen.lesson_id}, verified=${gen.verification?.verified}）`,
    JSON.stringify(
      {
        lesson_id: gen.lesson_id,
        verification: gen.verification,
        first_node: gen.spec?.activity_graph?.[0]?.prompt,
      },
      null,
      2,
    ),
  );

  // ④ render_lesson
  const rendered = await call("render_lesson", { spec: gen.spec });
  await addCard(
    "④ render_lesson(spec) — 真实可分享的课堂 URL（答案门控：未解锁节点无答案）",
    rendered.url ?? JSON.stringify(rendered),
  );

  // ⑤ 打开真实课堂并真实作答
  await page.goto(rendered.url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-activity-node]:visible");
  await sleep(2200);
  await page.fill("#answer-input", "6");
  await page.click("#submit-btn");
  await sleep(1800);

  await sleep(1200);
  const video = page.video();
  await context.close();
  const videoPath = await video.path();
  await browser.close();
  mcp.close();
  player.kill();

  console.log("[record] video:", videoPath);
  const { execFileSync } = await import("node:child_process");
  const ffmpeg = `${process.env.USERPROFILE}/AppData/Local/ms-playwright/ffmpeg-1011/ffmpeg-win64.exe`;
  mkdirSync(FRAMES, { recursive: true });
  // 注意：playwright 自带的 ffmpeg 是精简构建（无 fps/scale 滤镜），这里直接导全帧
  execFileSync(ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-i", videoPath, `${FRAMES}/f%04d.png`,
  ]);
  console.log("[record] frames:", FRAMES);
  console.log("[record] next: python scripts/frames_to_gif.py .gif-frames docs/assets/readme-demo.gif --step 3 --width 640 --duration 130");
}

main().catch((err) => {
  console.error("[record] failed:", err);
  process.exit(1);
});
