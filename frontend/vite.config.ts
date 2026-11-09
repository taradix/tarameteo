import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/healthz": { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "happy-dom",
    setupFiles: "./src/test/setup.ts",
    unstubGlobals: true,
    coverage: {
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/api-types.ts", "src/main.tsx", "src/test/**", "src/**/*.test.{ts,tsx}"],
      thresholds: { statements: 50, branches: 50, functions: 50, lines: 50 },
    },
  },
});
