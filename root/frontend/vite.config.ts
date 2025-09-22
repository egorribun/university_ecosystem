import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = (env.VITE_BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(/\/$/, "");

  const mk = (rewrite = false) => ({
    target,
    changeOrigin: true,
    ...(rewrite ? { rewrite: (p: string) => p.replace(/^\/api/, "") } : {})
  });

  const proxy = {
    "/api": mk(true),
    "/auth": mk(),
    "/static": mk(),
    "/media": mk(),
    "/spotify": mk(),
    "/notifications": mk(),
    "/push": mk()
  };

  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
    server: {
      host: true,
      cors: true,
      headers: { "Service-Worker-Allowed": "/" },
      proxy
    },
    preview: {
      host: true,
      headers: { "Service-Worker-Allowed": "/" },
      proxy
    }
  };
});