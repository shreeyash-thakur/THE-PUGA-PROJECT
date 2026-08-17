import { defineConfig } from "vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import { nitro } from "nitro/vite";

// Standalone, offline-friendly Vite config for PUGA. Previously this project
// used @lovable.dev/vite-tanstack-config, which wired up the same plugins
// plus Lovable's editor-preview integration (sandbox host detection, its
// hosted error telemetry, and a Cloudflare-flavoured Nitro default). None of
// that is needed to run PUGA locally/offline, so the plugins are configured
// directly here instead.
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
  },
  plugins: [
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
    tailwindcss(),
    tanstackStart({
      server: { entry: "server" },
    }),
    // node target: this app is meant to be run locally/offline, not deployed
    // to an edge platform.
    nitro({ config: { preset: "node-server" } }),
    viteReact(),
  ],
});
