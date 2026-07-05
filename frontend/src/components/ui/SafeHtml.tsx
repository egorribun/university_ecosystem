import { type ReactNode, useMemo } from "react"
import { sanitize_rich_text } from "wasm-sanitizer"
import { htmlToPlainText } from "@/utils/htmlText"

interface SafeHtmlProps {
  html: string
  className?: string
  fallback?: ReactNode
}

/**
 * A "World-Class" component for rendering sanitized HTML with WebAssembly ammonia.
 *
 * TD-W18-03 (audit 2026-03-23 Wave 18): wrapped in useMemo + try/catch to handle
 * the edge case where the WASM module has not yet finished initializing. Previously
 * the synchronous call during render could throw if init was still in progress.
 */
export default function SafeHtml({ html, className, fallback }: SafeHtmlProps) {
  const sanitized = useMemo(() => {
    try {
      return sanitize_rich_text(html)
    } catch {
      // WASM module not yet initialized — fall through to fallback.
      return null
    }
  }, [html])

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

  // The HTML is sanitized by wasm-sanitizer/ammonia (Rust, allowlist-based) then
  // checked for script/event-handler patterns above. This is the correct use of
  // dangerouslySetInnerHTML: sanitized content from a trusted WASM sanitizer.
  return <div className={className} dangerouslySetInnerHTML={{ __html: sanitized }} /> // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml
}
