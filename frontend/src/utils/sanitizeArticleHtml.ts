import { htmlToPlainText } from "@/utils/htmlText"

/**
 * Sanitizer for Markdown-rendered HTML in article bodies.
 *
 * The WASM ammonia sanitizer (SafeHtml) has a restricted allowlist that strips
 * GFM tables, images, and horizontal rules. This function keeps the broader
 * editorial HTML surface while removing active content structurally.
 */

const DANGEROUS_TAGS = new Set([
  "script",
  "style",
  "iframe",
  "object",
  "embed",
  "form",
  "input",
  "textarea",
  "select",
  "button",
])

const URL_ATTRIBUTES = new Set(["href", "src", "action"])
const SAFE_DATA_IMAGE_URL_PATTERN =
  /^data:image\/(?:avif|gif|jpeg|jpg|png|webp);base64,[a-z0-9+/=\s]+$/i

const getUrlProtocol = (value: string): string | null => {
  const compact = [...value.trim()]
    .filter((char) => {
      const code = char.charCodeAt(0)
      return code > 0x1f && code !== 0x7f && !/\s/.test(char)
    })
    .join("")
  if (!compact) return null

  try {
    return new URL(compact, "https://ue.local").protocol.toLowerCase()
  } catch {
    return null
  }
}

const isUnsafeUrlAttribute = (name: string, value: string): boolean => {
  const protocol = getUrlProtocol(value)
  if (!protocol) return true
  if (protocol === "javascript:" || protocol === "vbscript:" || protocol === "file:") {
    return true
  }
  if (protocol === "data:") {
    return name !== "src" || !SAFE_DATA_IMAGE_URL_PATTERN.test(value.trim())
  }
  return false
}

const sanitizeElement = (element: Element): void => {
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (name.startsWith("on")) {
      element.removeAttribute(attribute.name)
      continue
    }
    if (URL_ATTRIBUTES.has(name) && isUnsafeUrlAttribute(name, attribute.value)) {
      element.removeAttribute(attribute.name)
    }
  }
}

export function sanitizeArticleHtml(html: string): string {
  if (!html) return ""

  if (typeof document === "undefined") {
    return htmlToPlainText(html)
  }

  const template = document.createElement("template")
  template.innerHTML = html

  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT)
  const dangerousElements: Element[] = []
  const elements: Element[] = []

  while (walker.nextNode()) {
    const element = walker.currentNode as Element
    if (DANGEROUS_TAGS.has(element.tagName.toLowerCase())) {
      dangerousElements.push(element)
    } else {
      elements.push(element)
    }
  }

  for (const element of dangerousElements) {
    element.remove()
  }

  for (const element of elements) {
    if (template.content.contains(element)) sanitizeElement(element)
  }

  return template.innerHTML
}
