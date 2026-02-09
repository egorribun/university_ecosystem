import { useEffect, useState, type ReactNode } from "react"
import { sanitizeHTML } from "@/utils/trustedTypes"

interface SafeHtmlProps {
  html: string
  className?: string
  fallback?: ReactNode
}

/**
 * A "World-Class" component for rendering sanitized HTML with lazy-loaded DOMPurify.
 */
export default function SafeHtml({ html, className, fallback }: SafeHtmlProps) {
  const [sanitized, setSanitized] = useState<string | { toString(): string } | null>(null)

  useEffect(() => {
    let active = true

    async function run() {
      // sanitizeHTML will handle the dynamic import internally (to be refactored)
      const result = await sanitizeHTML(html)
      if (active) setSanitized(result as any)
    }

    run()
    return () => {
      active = false
    }
  }, [html])

  if (!sanitized) return <>{fallback ?? null}</>

  return <div className={className} dangerouslySetInnerHTML={{ __html: sanitized as any }} />
}




