import type { StorybookConfig } from "@storybook/react-vite"
import type { Plugin } from "vite"

const config: StorybookConfig = {
  // Wave 115 polish — restrict to `src/components/` so the glob doesn't
  // pick up TanStack Router files that happen to match `*.stories.tsx`
  // (e.g. `src/routes/_admin/admin.stories.tsx` — a route file, not a
  // Storybook story). The eslint `storybook/default-exports` rule is
  // also off for `src/routes/` per CLAUDE.md for the same reason.
  stories: ["../src/components/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: [
    "@chromatic-com/storybook",
    "@storybook/addon-vitest",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-onboarding",
  ],
  framework: "@storybook/react-vite",
  // Wave 120 SW8 (Wave 121 carry-over) — strip vite-plugin-pwa from the
  // Storybook Vite config. PWA's registerSW.js gets injected into
  // Storybook's iframe.html and registers a service worker that
  // intercepts the preview runtime, breaking story extraction with
  // `Error: __STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__ is not
  // defined` (Chromatic build #1+#2 failed on this). Wave 116 SW-Stretch
  // unblocked the BUILD via workbox cap raise but never disabled PWA;
  // process.env.STORYBOOK isn't set at vite.config.mts evaluation time
  // (per Wave 116 audit), so the strip has to happen here in viteFinal
  // where Storybook hands us its already-evaluated Vite config.
  async viteFinal(viteConfig) {
    // Vite plugins can be nested arrays (vite-plugin-pwa returns multiple
    // sub-plugins as an array from a single VitePWA() call). Flatten
    // recursively before filtering.
    const flatten = (arr: unknown[]): unknown[] =>
      arr.flatMap((item) => (Array.isArray(item) ? flatten(item) : [item]))
    const isPwaPlugin = (plugin: unknown): boolean => {
      if (!plugin || typeof plugin !== "object") return false
      const name = (plugin as { name?: string }).name
      return typeof name === "string" && name.startsWith("vite-plugin-pwa")
    }
    const allPlugins = flatten(viteConfig.plugins ?? []) as Plugin[]
    return {
      ...viteConfig,
      plugins: allPlugins.filter((p) => !isPwaPlugin(p)),
    }
  },
}
export default config
