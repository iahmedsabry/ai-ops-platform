import { defineConfig } from "vite";

/** Dev server for the legacy single-file SPA; `npm run build` copies `index.html` to `dist/` for GitOps. */
export default defineConfig({
  base: "/kai/",
  server: {
    port: 5173,
  },
});
