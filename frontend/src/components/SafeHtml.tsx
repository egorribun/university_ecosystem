import { useEffect, useState, type ReactNode } from "react"
import type { TrustedHTML } from "trusted-types/lib"
import { sanitizeHTML, getDOMPurifySync } from "@/utils/trustedTypes"

interface SafeHtmlProps {
  html: string
  className?: string
  fallback?: ReactNode
}

/**
 * A "World-Class" component for rendering sanitized HTML with lazy-loaded DOMPurify.
 */
export default function SafeHtml({ html, className, fallback }: SafeHtmlProps) {
  const [sanitized, setSanitized] = useState<string | TrustedHTML | null>(() => {
    // Attempt synchronous check first
    const instance = getDOMPurifySync()
    if (instance) {
       return instance.sanitize(html, { RETURN_TRUSTED_TYPE: false })
    }
    return null
  })

  useEffect(() => {
    let active = true

    async function run() {
      const instance = getDOMPurifySync()
      if (instance) {
        const syncResult = instance.sanitize(html, { RETURN_TRUSTED_TYPE: false })
        if (active) setSanitized(syncResult)
        return
      }

      const result = await sanitizeHTML(html)
      if (active) setSanitized(result)
    }

    run()
    return () => {
      active = false
    }
  }, [html])

  if (!sanitized) return <>{fallback ?? null}</>

  return <div className={className} dangerouslySetInnerHTML={{ __html: sanitized }} />
}
