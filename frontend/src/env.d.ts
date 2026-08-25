/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_ORIGIN?: string
  readonly VITE_APP_RELEASE?: string
  readonly VITE_ENVIRONMENT?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE?: string
  readonly VITE_SENTRY_PROFILES_SAMPLE_RATE?: string
  readonly VITE_OTEL_EXPORTER_OTLP_ENDPOINT?: string
  readonly VITE_OTEL_SERVICE_NAME?: string
  readonly VITE_SERVICE_VERSION?: string
  readonly VITE_VAPID_PUBLIC_KEY?: string
  readonly VITE_LHCI?: string
  readonly VITE_ENABLE_WEB_VITALS?: string
  readonly VITE_WEB_VITALS_ENDPOINT?: string
  readonly VITE_CWV_TRUSTED_RUM?: string
  readonly VITE_E2E_MODE?: string
  readonly VITE_RELEASE?: string
  readonly VITE_SENTRY_RELEASE?: string
  readonly VITE_QUERY_STALE_TIME_MS?: string
  readonly VITE_QUERY_CACHE_TTL_MS?: string
  readonly VITE_TRACE_HEADER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * Wave 148 SW2 — Hydration sentinel for Playwright e2e tests.
 *
 * Set to `true` by a useEffect in `AppProviders.tsx` AFTER React commits the
 * full provider tree (LanguageProvider → LazyMotion → MotionConfig →
 * ProvidersInner → AuthContext → WebSocketProvider → MessengerProvider).
 * `tests/e2e/url-state-persistence.spec.ts` uses
 * `page.waitForFunction(() => window.__APP_HYDRATED === true)` to gate
 * clicks/fills on controls that depend on onClick bindings from
 * useURLState — these bindings attach during React commit, AFTER main.tsx's
 * synchronous `#root.ready` class. Without the sentinel, Playwright clicks
 * the SSR'd button before React commits → URL doesn't update (W125 createRoot
 * SSR migration consequence per W147 §Honesty probe).
 *
 * NOT gated by VITE_LHCI or VITE_E2E_MODE — the sentinel ships in production
 * builds too (1-byte boolean, useful for prod debugging; test-only flags
 * would create prod-vs-test divergence risk).
 */
interface Window {
  __APP_HYDRATED?: boolean
  __UE_SELECTED_LANG__?: "ru" | "en"
}
