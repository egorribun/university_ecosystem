import type { StorybookConfig } from "@storybook/react-vite"
import type { Plugin, UserConfig } from "vite"

type RolldownOutput = { strictExecutionOrder?: boolean } & Record<string, unknown>
type RolldownOptions = { output?: RolldownOutput } & Record<string, unknown>
type RolldownBuild = { rolldownOptions?: RolldownOptions } & Record<string, unknown>
type ViteUserConfigWithRolldown = UserConfig & { build?: RolldownBuild }

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
    // Wave 125 Phase 2 — strip ONLY the TanStack Start sub-plugins that
    // conflict with Storybook's iframe build, NOT the whole chain.
    // Removing `tanstack-start-core:config` + `tanstack-react-start:config`
    // breaks dependent plugins (`Cannot get config before root is
    // resolved`) so they must stay; the start compiler, import protection,
    // and router-plugin are needed too because Storybook stories may
    // import server functions transitively.
    //
    // Plugins removed for Storybook:
    //   - tanstack-start-core:dev-server / preview-server — Storybook
    //     runs its own iframe server, doesn't need SSR middleware.
    //   - tanstack-start-core:start-manifest-capture-client-build —
    //     throws `Error: multiple entries detected: assets/index-XXX.js`
    //     because Storybook's iframe build emits multiple chunks (one
    //     per story bundle group); the manifest plugin assumes exactly
    //     one client entry.
    //   - tanstack-start-core:post-build — runs after our main app build,
    //     irrelevant to Storybook's static story output.
    //   - tanstack-start-core:virtual-client-entry — exposes the SPA
    //     client entry at `/_build/...`; Storybook ships its own iframe
    //     entry.
    const STORYBOOK_INCOMPATIBLE_TANSTACK_PLUGINS = new Set([
      "tanstack-start-core:dev-server",
      "tanstack-start-core:dev-server:injected-head-scripts",
      "tanstack-start-core:preview-server",
      "tanstack-start:start-manifest-capture-client-build",
      "tanstack-start-core:start-manifest-capture-client-build",
      "tanstack-start-core:post-build",
      "tanstack-start-core:virtual-client-entry",
      // Wave 125 — exact plugin name varies between
      // `tanstack-start:` and `tanstack-start-core:` prefixes depending
      // on which sub-package the plugin originates from. Both spellings
      // are filtered defensively.
    ])
    const isStorybookIncompatibleTanstackPlugin = (plugin: unknown): boolean => {
      if (!plugin || typeof plugin !== "object") return false
      const name = (plugin as { name?: string }).name
      return typeof name === "string" && STORYBOOK_INCOMPATIBLE_TANSTACK_PLUGINS.has(name)
    }
    const allPlugins = flatten(viteConfig.plugins ?? []) as Plugin[]
    // Wave 123 SW1 — Storybook 10 + Vite 8/Rolldown ships with `__STORYBOOK_MODULE_*`
    // globals that are READ by chunks but never assigned in the bundle. Rolldown's
    // module execution order optimization re-orders chunks, so Storybook's custom
    // module loader runs BEFORE the globals are wired up → `Uncaught ReferenceError:
    // __STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__ is not defined` at runtime.
    // Per vitejs/rolldown-vite#562 (closed as duplicate of vitejs/vite#21948,
    // closed 2026-04-07 by Vite 8.0.6), the canonical workaround is
    // `strictExecutionOrder: true` in rolldown output. Vite 8.0.6+ supposedly
    // resolves Lexical/Prism cases without it, but Storybook's custom module
    // loader still requires the explicit flag (chrome-devtools-mcp verified
    // 2026-04-30). This hook keeps the flag scoped to Storybook builds only,
    // so the main app bundle isn't affected.
    const buildConfig = (viteConfig as ViteUserConfigWithRolldown).build ?? {}
    const rolldownOpts = buildConfig.rolldownOptions ?? {}
    const rolldownOutput = rolldownOpts.output ?? {}
    return {
      ...viteConfig,
      plugins: allPlugins.filter(
        (p) => !isPwaPlugin(p) && !isStorybookIncompatibleTanstackPlugin(p)
      ),
      build: {
        ...buildConfig,
        rolldownOptions: {
          ...rolldownOpts,
          output: {
            ...rolldownOutput,
            strictExecutionOrder: true,
          },
        },
      },
    } as UserConfig
  },
}
export default config
