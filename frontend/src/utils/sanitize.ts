import type { TrustedHTML, TrustedTypePolicyFactory } from "trusted-types/lib"
import { logWarning } from "@/app/logger"
import { htmlToPlainText } from "@/utils/htmlText"

import { sanitize_rich_text, strip_html } from "wasm-sanitizer"

type TrustedPolicy = ReturnType<TrustedTypePolicyFactory["createPolicy"]>

// Configuration handled entirely in Wasm Rust code

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory
  __dompurifyNewsPolicy?: TrustedPolicy | false
}

const createPolicy = async (windowInstance: TrustedTypesWindow): Promise<TrustedPolicy | null> => {
  if (!windowInstance.trustedTypes) return null
  if (windowInstance.__dompurifyNewsPolicy === false) return null
  if (windowInstance.__dompurifyNewsPolicy) return windowInstance.__dompurifyNewsPolicy

  try {
    windowInstance.__dompurifyNewsPolicy = windowInstance.trustedTypes.createPolicy(
      "dompurify-news",
      {
        createHTML: (dirty: string) => sanitize_rich_text(dirty),
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

  if (typeof window !== "undefined") {
    const windowInstance = window as TrustedTypesWindow
    const policy = await createPolicy(windowInstance)
    if (policy) {
      return policy.createHTML(source)
    }
  }
  try {
    return sanitize_rich_text(source)
  } catch {
    // RZ-24-04: WASM fallback — render text only when wasm-sanitizer unavailable.
    return htmlToPlainText(source)
  }
}

export const sanitizeNewsText = async (dirty: string | null | undefined): Promise<string> => {
  const source = dirty ?? ""
  try {
    return strip_html(source)
  } catch {
    // RZ-24-04: WASM fallback — render text only when wasm-sanitizer unavailable.
    return htmlToPlainText(source)
  }
}

const TELEGRAM_HOSTS = new Set(["t.me", "telegram.me"])

export const sanitizeHttpUrl = (raw: string | null | undefined): string | null => {
  if (!raw) return null
  try {
    const base =
      typeof window !== "undefined" && typeof window.location?.origin === "string"
        ? window.location.origin
        : "about:blank"
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
  // TD-14-06: Validate Telegram username format — [a-zA-Z0-9_]{5,32}
  // Rejects path-traversal attempts like "../../admin" or empty strings.
  if (!/^[a-zA-Z0-9_]{5,32}$/.test(withoutPrefix)) return ""
  return `https://t.me/${withoutPrefix}`
}
