/**
 * 渲染服务：LessonSpec v2 → 可分享课堂 URL。
 *
 * - POST /lessons  {spec} → {url, id}：url 自包含（spec 以 base64url 编码进查询串），
 *   因此可分享、不依赖服务端状态、不过期。
 * - GET /lesson.html?spec=<base64url>：渲染页（载入 spec → renderLesson）。
 * - GET /dist|/templates|/demo：静态资源。
 * - GET /health：探活。
 *
 * 仅用 Node 内置模块（运行时依赖面保持 gsap-only）。
 */

import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_ROOT = fileURLToPath(new URL("..", import.meta.url));
const PORT = Number(process.env.PLAYER_PORT ?? process.argv[2] ?? 8130);
const HOST = process.env.PLAYER_HOST ?? "127.0.0.1";
const MAX_BODY = 4 * 1024 * 1024;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

/** 允许静态访问的目录（相对包根） */
const STATIC_ROOTS = ["dist", "templates", "demo"];

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new Error("payload too large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

/** 静态文件：限制在 STATIC_ROOTS 内，避免路径穿越 */
async function serveStatic(res, urlPath) {
  const rel = normalize(decodeURIComponent(urlPath)).replace(/^([/\\])+/, "");
  const top = rel.split(sep)[0];
  if (!STATIC_ROOTS.includes(top)) {
    sendJson(res, 404, { error: "not_found", detail: rel });
    return;
  }
  const filePath = join(PACKAGE_ROOT, rel);
  try {
    const data = await readFile(filePath);
    res.writeHead(200, {
      "content-type": MIME[extname(filePath)] ?? "application/octet-stream",
      "content-length": data.length,
      "cache-control": "no-cache",
    });
    res.end(data);
  } catch {
    sendJson(res, 404, { error: "not_found", detail: rel });
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { ok: true, service: "aiedu-player", version: "0.1.0" });
    return;
  }

  if (req.method === "POST" && url.pathname === "/lessons") {
    let spec;
    try {
      const raw = await readBody(req);
      spec = JSON.parse(raw);
    } catch (exc) {
      sendJson(res, 400, { error: "invalid_json", detail: String(exc) });
      return;
    }
    if (!spec || !Array.isArray(spec.activity_graph) || spec.activity_graph.length === 0) {
      sendJson(res, 400, {
        error: "invalid_spec",
        detail: "spec 必须含非空 activity_graph（LessonSpec v2）",
      });
      return;
    }
    const json = JSON.stringify(spec);
    const encoded = Buffer.from(json, "utf8").toString("base64url");
    const id = createHash("sha256").update(json).digest("hex").slice(0, 12);
    const base = `http://${HOST}:${PORT}`;
    sendJson(res, 200, {
      url: `${base}/lesson.html?spec=${encoded}`,
      id,
      lesson_id: spec.lesson_id ?? null,
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/lesson.html") {
    await serveStatic(res, "/templates/lesson/index.html");
    return;
  }

  if (req.method === "GET") {
    await serveStatic(res, url.pathname);
    return;
  }

  sendJson(res, 405, { error: "method_not_allowed" });
});

server.listen(PORT, HOST, () => {
  console.log(`aiedu-player render service listening on http://${HOST}:${PORT}`);
});
