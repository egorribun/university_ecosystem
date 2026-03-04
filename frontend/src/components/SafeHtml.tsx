import { type ReactNode } from "react"
import { sanitize_rich_text } from "wasm-sanitizer"

interface SafeHtmlProps {
  html: string
  className?: string
  fallback?: ReactNode
}

/**
 * A "World-Class" component for rendering sanitized HTML with WebAssembly ammonia.
 */
export default function SafeHtml({ html, className, fallback }: SafeHtmlProps) {
  const sanitized = sanitize_rich_text(html)

  if (!sanitized) return <>{fallback ?? null}</>

  return <div className={className} dangerouslySetInnerHTML={{ __html: sanitized }} />
}
