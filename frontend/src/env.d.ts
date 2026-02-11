/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_ORIGIN?: string
  readonly VITE_APP_RELEASE?: string
  readonly VITE_ENVIRONMENT?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE?: string
  readonly VITE_SENTRY_PROFILES_SAMPLE_RATE?: string
  readonly VITE_API_RATE_LIMIT_PER_MINUTE?: string
  readonly VITE_API_RATE_LIMIT_MAX_CONCURRENT?: string
  readonly VITE_VAPID_PUBLIC_KEY?: string
  readonly VITE_LHCI?: string
  readonly VITE_RELEASE?: string
  readonly VITE_SENTRY_RELEASE?: string
  readonly VITE_QUERY_STALE_TIME_MS?: string
  readonly VITE_QUERY_CACHE_TTL_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
