import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-server proxy means the React app can call same-origin `/api/*` paths
// during `npm run dev`, avoiding CORS entirely in local development.
// In production the built static files are served by nginx, which proxies
// `/api/*` to the backend container instead (see frontend/nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
