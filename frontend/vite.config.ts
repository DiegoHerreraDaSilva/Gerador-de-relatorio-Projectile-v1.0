import { defineConfig } from "vite";
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
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
