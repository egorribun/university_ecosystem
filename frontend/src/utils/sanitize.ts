import DOMPurify, { type Config } from "dompurify"
import type { TrustedHTML, TrustedTypePolicyFactory } from "trusted-types/lib"

type TrustedPolicy = ReturnType<TrustedTypePolicyFactory["createPolicy"]>

const HTML_CONFIG: Config = Object.freeze({
  USE_PROFILES: { html: true },
  ALLOW_DATA_ATTR: false,
  KEEP_CONTENT: false,
})

const TEXT_CONFIG: Config = Object.freeze({
  ALLOWED_TAGS: [],
  ALLOWED_ATTR: [],
  KEEP_CONTENT: false,
})

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory
  __dompurifyNewsPolicy?: TrustedPolicy | false
}

const createPolicy = (win: TrustedTypesWindow): TrustedPolicy | null => {
  if (!win.trustedTypes) return null
  if (win.__dompurifyNewsPolicy === false) return null
  if (win.__dompurifyNewsPolicy) return win.__dompurifyNewsPolicy
  try {
    win.__dompurifyNewsPolicy = win.trustedTypes.createPolicy("dompurify-news", {
      createHTML: (dirty: string) => DOMPurify.sanitize(dirty, HTML_CONFIG),
    })
  } catch (error) {
    console.warn("Unable to create dompurify-news trusted types policy", error)
    win.__dompurifyNewsPolicy = false
  }
  return win.__dompurifyNewsPolicy || null
}

export const sanitizeNewsHtml = (dirty: string | null | undefined): string | TrustedHTML => {
  const source = dirty ?? ""
  if (typeof window !== "undefined") {
    const win = window as TrustedTypesWindow
    const policy = createPolicy(win)
    if (policy) {
      return policy.createHTML(source)
    }
  }
  return DOMPurify.sanitize(source, HTML_CONFIG)
}

export const sanitizeNewsText = (dirty: string | null | undefined): string => {
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
