import { defineConfig } from "@playwright/test";

/**
 * 两个 webServer：
 * 1) 静态服务（包根）：供既有 9 个用例（/templates、/demo、/dist）；
 * 2) 渲染服务（server/serve.mjs）：供 ui-rules 用例跑真实渲染页面。
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:4173",
    viewport: { width: 1024, height: 768 },
  },
  webServer: [
    {
      command: "python -m http.server 4173 --directory .",
      url: "http://127.0.0.1:4173/templates/diagram/index.html",
      reuseExistingServer: true,
      timeout: 20000,
    },
    {
      command: "node server/serve.mjs 8130",
      url: "http://127.0.0.1:8130/health",
      reuseExistingServer: true,
      timeout: 20000,
    },
  ],
});
