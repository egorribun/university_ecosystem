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
    //
    // Wave 146 SW3 — CLEAR `environments` to restore Storybook's iframe.html input.
    //
    // Storybook's `codeGeneratorPlugin` (at `node_modules/@storybook/builder-
    // vite/dist/index.js`) sets `config.build.rollupOptions.input = iframePath`
    // during its `config(config, { command })` hook to point the build at
    // Storybook's iframe.html template (sourced from
    // `@storybook/builder-vite/input/iframe.html`).
    //
    // BUT TanStack Start's `tanstack-start-core:config` plugin (at
    // `node_modules/@tanstack/start-plugin-core/dist/esm/vite/plugin.js:83`)
    // returns `environments: viteConfigPlan.environments` — and that plan
    // (per `node_modules/@tanstack/start-plugin-core/dist/esm/vite/planning.js`
    // `createViteConfigPlan`) sets
    // `environments.<START_ENVIRONMENT_NAMES.client>.build.rollupOptions.input
    //   = { index: ENTRY_POINTS.client }` (the main-app SPA entry).
    //
    // In Vite 8's environments API, the per-environment `build.rollupOptions`
    // takes precedence over the top-level `build.rollupOptions` when the
    // matching environment runs. Storybook's preview build maps to the
    // "client" environment by default, so TanStack Start's `environments`
    // configuration WINS and Vite ends up building the SPA entry (main app)
    // instead of iframe.html. The result:
    //
    //   - `storybook-static/iframe.html` is NOT emitted at all (the input
    //     that would have produced it is missing)
    //   - `storybook-static/assets/*.js` is polluted with main-app chunks
    //     (`Dashboard-*.js`, `Activity-*.js`, `AdminAudit-*.js`, etc. — these
    //     are the SPA entry's transitive imports, not Storybook stories)
    //   - Chromatic's `validateFiles` rejects the build because iframe.html
    //     is required (preview iframe loads each story for screenshot
    //     capture)
    //
    // We CANNOT filter `tanstack-start-core:config` itself: per the W125 plan
    // comment above, removing it breaks every dependent plugin
    // (`Cannot get config before root is resolved`) — start compiler, import
    // protection, router-plugin all need it. So we KEEP the plugin and
    // override its output: clear `environments` so Storybook's top-level
    // `build.rollupOptions.input = iframe.html` is the only one Vite sees.
    //
    // Trade-off: TanStack Start's `define`, `resolve.noExternal`, and
    // `builder.buildApp` are also returned by the `:config` plugin — those
    // are still applied at the top level (only `environments` is on the
    // per-environment side). So clearing `environments` doesn't disable
    // TanStack Start's other functionality; it just stops the input override.
    // Storybook's preview build doesn't need TanStack Start's client/server
    // environment split — stories don't use server functions, and the build
    // output is a static iframe + chunk graph, not an SSR runtime.
    //
    // This is structurally cleaner than the Wave 146 SW3 first attempt
    // (merging rollupOptions into rolldownOptions). The first attempt
    // changed the dual-field shape but didn't address the higher-precedence
    // environments API override — iframe.html still missing after that fix.
    const buildConfig = (viteConfig as ViteUserConfigWithRolldown).build ?? {}
    const rolldownOpts = buildConfig.rolldownOptions ?? {}
    const rolldownOutput = rolldownOpts.output ?? {}

    // Wave 146 SW3 — POST plugin to clear `environments` set by TanStack
    // Start's `tanstack-start-core:config` (`enforce: 'pre'`).
    //
    // Diagnostic discovery: when viteFinal runs, `viteConfig.environments`
    // is empty + `build.rollupOptions.input` is null. TanStack Start's
    // `:config` plugin runs LATER (during Vite's actual build, not during
    // Storybook's viteFinal hook), so any direct override in the returned
    // config is silently re-overridden when the pre-plugin's `config()`
    // hook fires.
    //
    // Vite resolves plugin config() hooks in order: enforce:'pre' first,
    // normal plugins second, enforce:'post' last. So a post plugin's
    // config() hook fires AFTER tanstack-start-core:config (enforce:'pre')
    // and AFTER Storybook's codeGeneratorPlugin (enforce:'pre'), giving us
    // the final say in `environments` (clear it) and `build.rollupOptions`
    // (preserve Storybook's iframe.html input).
    //
    // This plugin clears `environments` so Vite falls back to the legacy
    // (non-environments-API) build pipeline using top-level
    // `build.rollupOptions.input` — which Storybook's codeGeneratorPlugin
    // sets to its iframe.html template path. Result: Vite emits iframe.html
    // as the build output, alongside chunk groups for the story imports.
    const clearTanStackEnvironmentsPlugin: Plugin = {
      name: "wave146-clear-tanstack-environments",
      enforce: "post",
      config(config) {
        // Clear environments so the per-environment build.rollupOptions.input
        // (set by TanStack Start to `ENTRY_POINTS.client`) doesn't override
        // Storybook's top-level build.rollupOptions.input (= iframe.html).
        ;(config as { environments?: unknown }).environments = undefined
      },
    }
    return {
      ...viteConfig,
      plugins: [
        ...allPlugins.filter((p) => !isPwaPlugin(p) && !isStorybookIncompatibleTanstackPlugin(p)),
        clearTanStackEnvironmentsPlugin,
      ],
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
