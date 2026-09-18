import { htmlToPlainText } from "@/utils/htmlText"

/**
 * Sanitizer for Markdown-rendered HTML in article bodies.
 *
 * The WASM ammonia sanitizer (SafeHtml) has a restricted allowlist that strips
 * GFM tables, images, and horizontal rules. This function keeps the required
 * editorial HTML surface while removing every unapproved element and attribute
 * structurally.
 */

const ALLOWED_TAGS = new Set([
  "p",
  "br",
  "b",
  "i",
  "strong",
  "em",
  "del",
  "s",
  "strike",
  "u",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "ul",
  "ol",
  "li",
  "blockquote",
  "pre",
  "code",
  "a",
  "img",
  "table",
  "thead",
  "tbody",
  "tfoot",
  "tr",
  "th",
  "td",
  "hr",
])

const HEADING_TAGS = new Set(["h1", "h2", "h3", "h4", "h5", "h6"])

const ALLOWED_ATTRIBUTES: Readonly<Record<string, ReadonlySet<string>>> = {
  a: new Set(["href", "title", "target", "rel"]),
  img: new Set(["src", "alt", "title", "width", "height", "loading", "decoding"]),
  table: new Set(["align"]),
  th: new Set(["align", "colspan", "rowspan"]),
  td: new Set(["align", "colspan", "rowspan"]),
  pre: new Set(["class"]),
  code: new Set(["class"]),
}

const URL_ATTRIBUTES = new Set(["href", "src"])
const SAFE_PROTOCOLS = new Set(["http:", "https:"])
const SAFE_ID_PATTERN = /^[\p{L}\p{N}_-]{1,64}$/u
const SAFE_CODE_CLASS_PATTERN = /^language-[a-z0-9_+-]+$/i
const SAFE_ALIGN_VALUES = new Set(["left", "center", "right", "justify"])
const SAFE_TARGET_VALUES = new Set(["_self", "_blank", "_parent", "_top"])
const SAFE_LOADING_VALUES = new Set(["eager", "lazy"])
const SAFE_DECODING_VALUES = new Set(["sync", "async", "auto"])

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
  if (protocol === "data:") {
    return name !== "src" || !SAFE_DATA_IMAGE_URL_PATTERN.test(value.trim())
  }
  return !SAFE_PROTOCOLS.has(protocol)
}

const sanitizeElement = (element: Element): void => {
  const tagName = element.tagName.toLowerCase()
  const allowedAttributes = new Set(ALLOWED_ATTRIBUTES[tagName] ?? [])
  if (HEADING_TAGS.has(tagName)) allowedAttributes.add("id")

  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (!allowedAttributes.has(name)) {
      element.removeAttribute(attribute.name)
      continue
    }

    if (URL_ATTRIBUTES.has(name)) {
      const isAllowedUrlAttribute =
        (tagName === "a" && name === "href") || (tagName === "img" && name === "src")
      if (!isAllowedUrlAttribute || isUnsafeUrlAttribute(name, attribute.value)) {
        element.removeAttribute(attribute.name)
      }
      continue
    }

    if (name === "id" && !SAFE_ID_PATTERN.test(attribute.value)) {
      element.removeAttribute(attribute.name)
      continue
    }

    if (name === "class") {
      const safeClasses = attribute.value
        .split(/\s+/)
        .filter((token) => SAFE_CODE_CLASS_PATTERN.test(token))
      if (safeClasses.length === 0) element.removeAttribute(attribute.name)
      else element.setAttribute(attribute.name, safeClasses.join(" "))
      continue
    }

    if (name === "align") {
      const value = attribute.value.trim().toLowerCase()
      if (!SAFE_ALIGN_VALUES.has(value)) element.removeAttribute(attribute.name)
      else element.setAttribute(attribute.name, value)
      continue
    }

    if (name === "target") {
      const value = attribute.value.trim().toLowerCase()
      if (!SAFE_TARGET_VALUES.has(value)) {
        element.removeAttribute(attribute.name)
      } else {
        element.setAttribute(attribute.name, value)
      }
      continue
    }

    if (name === "loading" && !SAFE_LOADING_VALUES.has(attribute.value.trim().toLowerCase())) {
      element.removeAttribute(attribute.name)
      continue
    }

    if (name === "decoding" && !SAFE_DECODING_VALUES.has(attribute.value.trim().toLowerCase())) {
      element.removeAttribute(attribute.name)
    }
  }

  if (tagName === "a" && element.getAttribute("target")?.toLowerCase() === "_blank") {
    const rel = new Set((element.getAttribute("rel") ?? "").split(/\s+/).filter(Boolean))
    rel.delete("opener")
    rel.add("noopener")
    rel.add("noreferrer")
    element.setAttribute("rel", Array.from(rel).join(" "))
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
  const removedElements: Element[] = []
  const elements: Element[] = []

  while (walker.nextNode()) {
    const element = walker.currentNode as Element
    if (!ALLOWED_TAGS.has(element.tagName.toLowerCase())) {
      removedElements.push(element)
    } else {
      elements.push(element)
    }
  }

  for (const element of removedElements) {
    element.remove()
  }

  for (const element of elements) {
    if (template.content.contains(element)) sanitizeElement(element)
  }

  return template.innerHTML
}
