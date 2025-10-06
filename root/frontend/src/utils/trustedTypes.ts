import DOMPurify, { type Config } from "dompurify"
import type {
  TrustedScriptURL,
  TrustedTypePolicy,
  TrustedTypePolicyFactory,
} from "trusted-types/lib"

const DEFAULT_POLICY_NAME = "default"
const APP_POLICY_NAME = "app"

const DEFAULT_SANITIZE_CONFIG: Config = Object.freeze({
  RETURN_TRUSTED_TYPE: false,
})

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory
  __ttDefaultPolicy?: TrustedTypePolicy | false
  __ttAppPolicy?: TrustedTypePolicy | false
}

const getAllowedScriptOrigins = (base: Location): Set<string> => {
  const origins = new Set<string>()
  try {
    origins.add(new URL(base.href).origin)
  } catch (error) {
    console.warn("Unable to resolve current origin for trusted types", error)
  }

  const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN
  if (backendOrigin) {
    try {
      origins.add(new URL(backendOrigin, base.href).origin)
    } catch (error) {
      console.warn("Invalid VITE_BACKEND_ORIGIN for trusted types", error)
    }
  }

  return origins
}

const ensureDefaultPolicy = (win: TrustedTypesWindow): TrustedTypePolicy | null => {
  if (!win.trustedTypes) return null
  if (win.__ttDefaultPolicy === false) return null
  if (win.__ttDefaultPolicy) return win.__ttDefaultPolicy
  try {
    win.__ttDefaultPolicy = win.trustedTypes.createPolicy(DEFAULT_POLICY_NAME, {
      createHTML: (input: string) => DOMPurify.sanitize(input, DEFAULT_SANITIZE_CONFIG),
    })
  } catch (error) {
    console.warn("Unable to register default trusted types policy", error)
    win.__ttDefaultPolicy = false
  }
  return win.__ttDefaultPolicy || null
}

const ensureAppPolicy = (win: TrustedTypesWindow): TrustedTypePolicy | null => {
  if (!win.trustedTypes) return null
  if (win.__ttAppPolicy === false) return null
  if (win.__ttAppPolicy) return win.__ttAppPolicy
  const location = win.location
  const allowed = getAllowedScriptOrigins(location)
  try {
    win.__ttAppPolicy = win.trustedTypes.createPolicy(APP_POLICY_NAME, {
      createScriptURL: (value: string) => {
        const resolved = new URL(value, location.href)
        if (!allowed.has(resolved.origin)) {
          throw new TypeError(`Blocked script origin: ${resolved.origin}`)
        }
        return resolved.toString()
      },
    })
  } catch (error) {
    console.warn("Unable to register app trusted types policy", error)
    win.__ttAppPolicy = false
  }
  return win.__ttAppPolicy || null
}

export const ensureTrustedTypesPolicies = (): void => {
  if (typeof window === "undefined") return
  const win = window as TrustedTypesWindow
  if (!win.trustedTypes) return
  ensureDefaultPolicy(win)
  ensureAppPolicy(win)
}

export const createTrustedScriptURL = (
  value: string,
): string | TrustedScriptURL => {
  if (typeof window === "undefined") return value
  const win = window as TrustedTypesWindow
  if (!win.trustedTypes) return value
  const policy = ensureAppPolicy(win)
  if (!policy) return value
  try {
    return policy.createScriptURL(value)
  } catch (error) {
    console.error("Failed to create TrustedScriptURL", error)
    return value
  }
}
