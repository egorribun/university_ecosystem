import type { TrustedHTML, TrustedTypePolicyFactory } from "trusted-types/lib"
import { logWarning } from "@/app/logger"

let dompurifyInstance: (typeof import("dompurify"))["default"] | null = null
async function getDOMPurify() {
  if (dompurifyInstance) return dompurifyInstance
  const DOMPurify = (await import("dompurify")).default
  dompurifyInstance = DOMPurify
  return dompurifyInstance
}

type TrustedPolicy = ReturnType<TrustedTypePolicyFactory["createPolicy"]>

const HTML_CONFIG = Object.freeze({
  USE_PROFILES: { html: true },
  ALLOW_DATA_ATTR: false,
  KEEP_CONTENT: false,
})

const TEXT_CONFIG = Object.freeze({
  ALLOWED_TAGS: [],
  ALLOWED_ATTR: [],
  KEEP_CONTENT: false,
})

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory
  __dompurifyNewsPolicy?: TrustedPolicy | false
}

const createPolicy = async (windowInstance: TrustedTypesWindow): Promise<TrustedPolicy | null> => {
  if (!windowInstance.trustedTypes) return null
  if (windowInstance.__dompurifyNewsPolicy === false) return null
  if (windowInstance.__dompurifyNewsPolicy) return windowInstance.__dompurifyNewsPolicy

  const DOMPurify = await getDOMPurify()

  try {
    windowInstance.__dompurifyNewsPolicy = windowInstance.trustedTypes.createPolicy(
      "dompurify-news",
      {
        createHTML: (dirty: string) => DOMPurify.sanitize(dirty, HTML_CONFIG),
      }
    )
  } catch (error) {
    logWarning("Unable to create dompurify-news trusted types policy", { error })
    windowInstance.__dompurifyNewsPolicy = false
  }
  return windowInstance.__dompurifyNewsPolicy || null
}

export const sanitizeNewsHtml = async (
  dirty: string | null | undefined
): Promise<string | TrustedHTML> => {
  const source = dirty ?? ""
  const DOMPurify = await getDOMPurify()

  if (typeof window !== "undefined") {
    const windowInstance = window as TrustedTypesWindow
    const policy = await createPolicy(windowInstance)
    if (policy) {
      return policy.createHTML(source)
    }
  }
  return DOMPurify.sanitize(source, HTML_CONFIG)
}

export const sanitizeNewsText = async (dirty: string | null | undefined): Promise<string> => {
  const DOMPurify = await getDOMPurify()
  return DOMPurify.sanitize(dirty ?? "", TEXT_CONFIG) as string
}

const DEFAULT_BASE = "http://localhost"
const TELEGRAM_HOSTS = new Set(["t.me", "telegram.me"])

export const sanitizeHttpUrl = (raw: string | null | undefined): string | null => {
  if (!raw) return null
  try {
    const base =
      typeof window !== "undefined" && typeof window.location?.href === "string"
        ? window.location.href
        : DEFAULT_BASE
    const parsed = new URL(raw, base)
    const protocol = parsed.protocol.toLowerCase()
    if (protocol !== "http:" && protocol !== "https:") return null
    if (parsed.username || parsed.password) return null
    return parsed.toString()
  } catch {
    return null
  }
}

export const sanitizeEmailAddress = (raw: string | null | undefined): string => {
  if (!raw) return ""
  const email = String(raw).trim()
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : ""
}

export const sanitizeTelegramUrl = (raw: string | null | undefined): string => {
  if (!raw) return ""
  const trimmed = String(raw).trim()
  if (!trimmed) return ""

  if (trimmed.startsWith("http")) {
    const safe = sanitizeHttpUrl(trimmed)
    if (!safe) return ""
    try {
      const parsed = new URL(safe)
      if (!TELEGRAM_HOSTS.has(parsed.hostname.toLowerCase())) return ""
      return parsed.toString()
    } catch {
      return ""
    }
  }

  const withoutPrefix = trimmed.replace(/^@+/, "")
  if (!withoutPrefix) return ""
  return `https://t.me/${encodeURIComponent(withoutPrefix)}`
}
