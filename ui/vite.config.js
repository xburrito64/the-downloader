import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The UI is built once into ui/dist. The engine serves those files; Node is not needed to run the app.
export default defineConfig({
  plugins: [svelte()],
  build: { target: "esnext", assetsInlineLimit: 0 },
});
