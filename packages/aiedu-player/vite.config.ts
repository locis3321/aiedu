/**
 * vite 构建：src/index.ts → dist/player.js
 * IIFE（classic script，file:// 可用）；GSAP 一并打包，无 CDN。
 */
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/index.ts",
      name: "AIEduPlayer",
      formats: ["iife"],
      fileName: () => "player.js",
    },
    outDir: "dist",
    emptyOutDir: true,
    target: "es2020",
  },
});
