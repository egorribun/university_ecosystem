/**
 * Sanitizer for Markdown-rendered HTML in article bodies.
 *
 * The WASM ammonia sanitizer (SafeHtml) has a restricted allowlist that strips
 * GFM tables, images, and horizontal rules. This function provides a broader
 * allowlist suitable for editorial content while blocking XSS vectors.
 *
 * Security model:
 * - `marked` escapes raw HTML in Markdown input by default
 * - This function provides defense-in-depth by stripping dangerous elements
 *   even if marked's escaping were bypassed
 */

const DANGEROUS_TAGS =
  /<\/?(?:script|style|iframe|object|embed|form|input|textarea|select|button)\b[^>]*>/gi
const EVENT_HANDLERS = /\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)/gi
const JS_URLS = /(?:href|src|action)\s*=\s*(?:"javascript:[^"]*"|'javascript:[^']*')/gi
const DATA_URLS = /(?:src)\s*=\s*(?:"data:(?!image\/)[^"]*"|'data:(?!image\/)[^']*')/gi

export function sanitizeArticleHtml(html: string): string {
  if (!html) return ""

  const clean = html
    .replace(DANGEROUS_TAGS, "")
    .replace(EVENT_HANDLERS, "")
    .replace(JS_URLS, "")
    .replace(DATA_URLS, "")

  // Defense-in-depth: reject entirely if script patterns survive
  if (/<script[\s>]/i.test(clean) || /\bon\w+\s*=/i.test(clean)) {
    return html.replace(/<[^>]*>/g, "")
  }

  return clean
}
