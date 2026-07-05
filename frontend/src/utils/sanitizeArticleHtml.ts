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

const isUnsafeUrlAttribute = (name: string, value: string): boolean => {
  const normalized = value.trim().toLowerCase()
  if (normalized.startsWith("javascript:")) return true
  if (name === "src" && normalized.startsWith("data:")) {
    return !normalized.startsWith("data:image/")
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
