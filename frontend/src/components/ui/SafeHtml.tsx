import { type ReactNode, useEffect, useMemo, useState } from "react"
import type { TrustedHTML } from "trusted-types/lib"
import { sanitize_rich_text } from "wasm-sanitizer"
import { htmlToPlainText } from "@/utils/htmlText"
import { getAppTrustedTypesPolicy } from "@/utils/trustedTypes"
import { ensureWasmSanitizerInitialized } from "@/utils/wasmSanitizer"

interface SafeHtmlProps {
  html: string
  className?: string
  fallback?: ReactNode
}

type TrustedTypesWindow = Window & { trustedTypes?: unknown }

/** Render allowlist-sanitized article HTML after browser WASM initialization. */
export default function SafeHtml({ html, className, fallback }: SafeHtmlProps) {
  const [wasmReady, setWasmReady] = useState(false)
  const sanitized = useMemo(() => {
    if (!wasmReady) return null
    try {
      return sanitize_rich_text(html)
    } catch {
      // Sanitization failed — fall through to the fallback below.
    }
    return null
  }, [html, wasmReady])

  useEffect(() => {
    if (wasmReady) return
    let active = true
    void ensureWasmSanitizerInitialized().then((ready) => {
      if (active && ready) setWasmReady(true)
    })
    return () => {
      active = false
    }
  }, [html, wasmReady])

  if (!sanitized) {
    if (fallback != null) return <>{fallback}</>
    // RZ-24-04: text-only fallback rather than rendering nothing.
    const textOnly = htmlToPlainText(html)
    return <span className={className}>{textOnly}</span>
  }

  // RZ-43-01: Defense-in-depth — reject if sanitizer output still contains
  // script injection patterns (should never happen with ammonia, but protects
  // against hypothetical sanitizer bypass vulnerabilities).
  if (/<script[\s>]/i.test(sanitized) || /\bon\w+\s*=/i.test(sanitized)) {
    const textOnly = htmlToPlainText(html)
    return <span className={className}>{textOnly}</span>
  }

  let renderable: string | TrustedHTML | null = sanitized
  if ((window as TrustedTypesWindow).trustedTypes) {
    try {
      const policy = getAppTrustedTypesPolicy()
      renderable = policy ? policy.createHTML(sanitized) : null
    } catch {
      renderable = null
    }
  }

  if (!renderable) {
    if (fallback != null) return <>{fallback}</>
    return <span className={className}>{htmlToPlainText(html)}</span>
  }

  // The HTML is sanitized by wasm-sanitizer/ammonia (Rust, allowlist-based) then
  // checked for script/event-handler patterns above. When Trusted Types is
  // available the existing app policy also sanitizes and brands the output.
  return <div className={className} dangerouslySetInnerHTML={{ __html: renderable }} />
}
