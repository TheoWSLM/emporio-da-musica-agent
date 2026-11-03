import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// In development, /api goes to the running stack (Caddy on EDGE_PORT); in production Caddy serves both.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://127.0.0.1:18082",
      },
    },
  },
});
