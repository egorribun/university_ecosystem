import type {
  TrustedHTML,
  TrustedScriptURL,
  TrustedTypePolicy,
  TrustedTypePolicyFactory,
} from "trusted-types/lib"

const SANITIZE_POLICY_NAME = "dompurify-news"
const APP_POLICY_NAME = "app"

let dompurifyInstance: (typeof import("dompurify"))["default"] | null = null
async function getDOMPurify() {
  if (dompurifyInstance) return dompurifyInstance
  const DOMPurify = (await import("dompurify")).default
  dompurifyInstance = DOMPurify
  return dompurifyInstance
}

export function getDOMPurifySync() {
  return dompurifyInstance
}

const DEFAULT_SANITIZE_CONFIG = Object.freeze({
  RETURN_TRUSTED_TYPE: false,
})

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

  const DOMPurify = await getDOMPurify()

  try {
    const policy = win.trustedTypes.createPolicy(SANITIZE_POLICY_NAME, {
      createHTML: (input: string) => DOMPurify.sanitize(input, DEFAULT_SANITIZE_CONFIG),
    }) as TrustedTypePolicy
    win.__ttSanitizePolicy = policy
  } catch {
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
        // Use synchronous DOMPurify if already loaded; otherwise reject.
        // DOMPurify is loaded lazily by ensureTrustedTypesPolicies() before any HTML
        // rendering occurs, so getDOMPurifySync() should always return a value here.
        const purify = getDOMPurifySync()
        if (!purify) {
          throw new TypeError("DOMPurify not loaded — refusing createHTML via app policy")
        }
        return purify.sanitize(value, DEFAULT_SANITIZE_CONFIG)
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
  const DOMPurify = await getDOMPurify()
  if (typeof window === "undefined") return DOMPurify.sanitize(value, DEFAULT_SANITIZE_CONFIG)
  const win = window as TrustedTypesWindow
  const policy = await ensureSanitizePolicy(win)
  if (policy) {
    try {
      return policy.createHTML(value)
    } catch {
      // ignore
    }
  }
  return DOMPurify.sanitize(value, DEFAULT_SANITIZE_CONFIG)
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
