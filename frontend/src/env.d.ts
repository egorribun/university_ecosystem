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
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}




