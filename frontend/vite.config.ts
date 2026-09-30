import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/parse": "http://localhost:8011",
      "/parse-db": "http://localhost:8011",
      "/generate": "http://localhost:8011",
      "/chat": "http://localhost:8011",
      "/auth": "http://localhost:8011",
      "/reports": "http://localhost:8011",
      "/artifacts": "http://localhost:8011",
      "/analytics": "http://localhost:8011",
      "/auto-generation": "http://localhost:8011",
      "/my-reviews": "http://localhost:8011",
      "/management": "http://localhost:8011",
      "/my-hours": "http://localhost:8011",
      "/send-report": "http://localhost:8011",
      "/translate-activities": "http://localhost:8011",
      "/health": "http://localhost:8011",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
