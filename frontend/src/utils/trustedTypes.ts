import type {
  TrustedHTML,
  TrustedScriptURL,
  TrustedTypePolicy,
  TrustedTypePolicyFactory,
} from "trusted-types/lib"

import { sanitize_rich_text } from "wasm-sanitizer"

const SANITIZE_POLICY_NAME = "wasm-sanitizer"
const APP_POLICY_NAME = "app"

// Wasm handles everything internally. No dompurify RETURN_TRUSTED_TYPE flag required.

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory
  __ttSanitizePolicy?: TrustedTypePolicy | false
  __ttAppPolicy?: TrustedTypePolicy | false
}

const getAllowedScriptOrigins = (base: Location): Set<string> => {
  const origins = new Set<string>()
  try {
    origins.add(new URL(base.href).origin)
  } catch {
    // ignore
  }
  const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN
  if (backendOrigin) {
    try {
      origins.add(new URL(backendOrigin, base.href).origin)
    } catch {
      // ignore
    }
  }
  return origins
}

const ensureSanitizePolicy = async (win: TrustedTypesWindow): Promise<TrustedTypePolicy | null> => {
  if (!win.trustedTypes) return null
  if (win.__ttSanitizePolicy === false) return null
  if (win.__ttSanitizePolicy) return win.__ttSanitizePolicy

  try {
    const policy = win.trustedTypes.createPolicy(SANITIZE_POLICY_NAME, {
      createHTML: (input: string) => sanitize_rich_text(input),
    }) as TrustedTypePolicy
    win.__ttSanitizePolicy = policy
  } catch (err) {
    // RED-01 (audit Wave 11): Log security-critical failure — propagates to Sentry
    // via the global window.onerror / unhandledrejection handler if configured.
    // Previously silent, making WASM policy failures undetectable in production.
    console.error("[TrustedTypes] Failed to create sanitize policy — HTML sanitization may be degraded:", err)
    win.__ttSanitizePolicy = false
  }
  return win.__ttSanitizePolicy || null
}

const ensureAppPolicy = (win: TrustedTypesWindow): TrustedTypePolicy | null => {
  if (!win.trustedTypes) return null
  if (win.__ttAppPolicy === false) return null
  if (win.__ttAppPolicy) return win.__ttAppPolicy
  const location = win.location
  const allowed = getAllowedScriptOrigins(location)
  try {
    const policy = win.trustedTypes.createPolicy(APP_POLICY_NAME, {
      createScriptURL: (value: string) => {
        const resolved = new URL(value, location.href)
        if (!allowed.has(resolved.origin)) {
          throw new TypeError(`Blocked script origin: ${resolved.origin}`)
        }
        return resolved.toString()
      },
      createHTML: (value: string) => {
        return sanitize_rich_text(value)
      },
    }) as TrustedTypePolicy
    win.__ttAppPolicy = policy
  } catch {
    win.__ttAppPolicy = false
  }
  return win.__ttAppPolicy || null
}

export const ensureTrustedTypesPolicies = async (): Promise<void> => {
  if (typeof window === "undefined") return
  const win = window as TrustedTypesWindow
  if (!win.trustedTypes) return
  await ensureSanitizePolicy(win)
  ensureAppPolicy(win)
}

export const sanitizeHTML = async (value: string): Promise<string | TrustedHTML> => {
  if (typeof window === "undefined") return sanitize_rich_text(value)
  const win = window as TrustedTypesWindow
  const policy = await ensureSanitizePolicy(win)
  if (policy) {
    // RED-01 (audit Wave 11): Do NOT swallow createHTML errors — a throw here means
    // the sanitizer actively rejected the input. Propagate so callers can show an
    // error state rather than silently rendering unsanitized HTML.
    return policy.createHTML(value)
  }
  // No TrustedTypes support in this browser / SSR environment: call sanitizer directly.
  // This path is only reached when win.trustedTypes is falsy (pre-TT browser or Node.js).
  return sanitize_rich_text(value)
}

export const createTrustedScriptURL = (value: string): string | TrustedScriptURL => {
  if (typeof window === "undefined") return value
  const win = window as TrustedTypesWindow
  const policy = ensureAppPolicy(win)
  if (!policy) return value
  try {
    return policy.createScriptURL(value)
  } catch {
    return value
  }
}
