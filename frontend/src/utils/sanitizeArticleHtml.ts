import { createElement, type ReactNode } from "react"
import { parseFragment, type DefaultTreeAdapterTypes } from "parse5"
import type { TrustedHTML } from "trusted-types/lib"
import { htmlToPlainText } from "@/utils/htmlText"
import { getAppTrustedTypesPolicy } from "@/utils/trustedTypes"

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

// The native sanitizer parses without an innerHTML sink. Its broad attribute
// list is narrowed per element by sanitizeElement below.
const NATIVE_ARTICLE_SANITIZER = {
  elements: [...ALLOWED_TAGS],
  attributes: [
    ...new Set(["id", ...Object.values(ALLOWED_ATTRIBUTES).flatMap((names) => [...names])]),
  ],
}

type SafeHtmlTemplate = HTMLTemplateElement & {
  setHTML?: (html: string, options: { sanitizer: typeof NATIVE_ARTICLE_SANITIZER }) => void
}

type TrustedTypesGlobal = Window & { trustedTypes?: unknown }

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

const isUnsafeUrlAttribute = (name: string, value: string): boolean => {
  // Judge the scheme without control characters and whitespace, so an
  // obfuscated "java\tscript:" is rejected rather than read as a relative URL.
  const compact = [...value]
    .filter((char) => {
      const code = char.charCodeAt(0)
      return code > 0x1f && code !== 0x7f && !/\s/.test(char)
    })
    .join("")
  if (!compact) return true

  let url: URL
  try {
    url = new URL(compact, "https://ue.local")
  } catch {
    return true
  }
  // URL.protocol is always lower-case.
  if (url.protocol === "data:") {
    return name !== "src" || !SAFE_DATA_IMAGE_URL_PATTERN.test(value.trim())
  }
  return !SAFE_PROTOCOLS.has(url.protocol)
}

const hasEntityReference = (value: string): boolean => /&(?:#|[a-z])/i.test(value)

/** Extracts parse5 text nodes so decoded `<` characters are never reparsed as markup. */
const decodeHtmlText = (value: string): string => {
  if (!hasEntityReference(value)) return value
  const fragment = parseFragment(value.replace(/</g, "&#60;"))
  return fragment.childNodes
    .map((node) => (node as DefaultTreeAdapterTypes.TextNode).value)
    .join("")
}

/** Decodes HTML5 character references in ordinary text, consistently on SSR and in browsers. */
export const decodeArticleText = decodeHtmlText

const NON_VISIBLE_TEXT_TAGS = new Set(["script", "style", "template", "noscript"])

/**
 * Returns the visible text of an HTML fragment from parse5's tree, for rendering as
 * plain text. Parsing rather than pattern matching leaves no partial tag behind.
 */
export const articleHtmlToText = (source: string): string => {
  const parts: string[] = []
  const pending: DefaultTreeAdapterTypes.ChildNode[] = [...parseFragment(source).childNodes]
  pending.reverse()
  for (let node = pending.pop(); node !== undefined; node = pending.pop()) {
    if (node.nodeName === "#text") {
      parts.push((node as DefaultTreeAdapterTypes.TextNode).value)
    } else if ("childNodes" in node && !NON_VISIBLE_TEXT_TAGS.has(node.nodeName)) {
      pending.push(...[...node.childNodes].reverse())
    }
  }
  return parts.join("")
}

/** Decodes references using HTML attribute parsing rules without allowing attribute breakout. */
export const decodeArticleAttribute = (value: string): string => {
  if (!hasEntityReference(value)) return value
  const quotedValue = value.replace(/"/g, "&quot;").replace(/</g, "&lt;")
  const fragment = parseFragment(`<a href="${quotedValue}"></a>`)
  const anchor = fragment.childNodes[0] as DefaultTreeAdapterTypes.Element
  return anchor.attrs[0]!.value
}

const sanitizeUrlValue = (name: "href" | "src", value: string, decode: boolean): string | null => {
  const normalized = (decode ? decodeArticleAttribute(value) : value).trim()
  return normalized && !isUnsafeUrlAttribute(name, normalized) ? normalized : null
}

/** Returns a safe http(s), relative, or fragment article URL. */
export const sanitizeArticleUrl = (name: "href" | "src", value: string): string | null => {
  return sanitizeUrlValue(name, value, true)
}

const sanitizeElement = (element: Element): void => {
  const tagName = element.tagName.toLowerCase()
  const allowedAttributes = new Set<string>(ALLOWED_ATTRIBUTES[tagName])
  if (HEADING_TAGS.has(tagName)) allowedAttributes.add("id")

  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (!allowedAttributes.has(name)) {
      element.removeAttribute(attribute.name)
      continue
    }

    // The allowlist admits URL attributes only as <a href> and <img src>.
    if (URL_ATTRIBUTES.has(name)) {
      const safeUrl = sanitizeUrlValue(name as "href" | "src", attribute.value, false)
      if (safeUrl === null) element.removeAttribute(attribute.name)
      else element.setAttribute(name, safeUrl)
      continue
    }

    if (name === "id" && !SAFE_ID_PATTERN.test(attribute.value)) {
      element.removeAttribute(attribute.name)
      continue
    }

    if (name === "class") {
      const safeClasses = Array.from(element.classList).filter((token) =>
        SAFE_CODE_CLASS_PATTERN.test(token)
      )
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

  // Only <a> may keep target, and the loop above normalized it to lower case.
  if (element.getAttribute("target") === "_blank") {
    const rel = new Set((element as HTMLAnchorElement).relList)
    rel.delete("opener")
    rel.add("noopener")
    rel.add("noreferrer")
    element.setAttribute("rel", Array.from(rel).join(" "))
  }
}

function sanitizeTemplate(template: HTMLTemplateElement): void {
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

  // Descendants of removed elements are detached; sanitizing them is harmless.
  for (const element of elements) sanitizeElement(element)
}

const isTrustedTypesEnforced = (): boolean =>
  typeof window !== "undefined" && Boolean((window as TrustedTypesGlobal).trustedTypes)

const createSafeTemplate = (): SafeHtmlTemplate =>
  document.createElement("template") as SafeHtmlTemplate

/**
 * Markdown headings receive ids in the renderer, but the WASM ammonia allowlist
 * (used by the app policy) drops every id attribute. Restore the ids in document
 * order; a count mismatch leaves the markup untouched rather than guessing.
 */
const restoreHeadingIds = (root: DocumentFragment, headingIds: readonly string[]): void => {
  const headings = root.querySelectorAll("h1, h2, h3, h4, h5, h6")
  if (headings.length !== headingIds.length) return
  headings.forEach((heading, index) => {
    const id = headingIds[index] ?? ""
    if (!heading.hasAttribute("id") && SAFE_ID_PATTERN.test(id)) heading.setAttribute("id", id)
  })
}

const finishTemplate = (
  template: HTMLTemplateElement,
  headingIds: readonly string[]
): HTMLTemplateElement => {
  sanitizeTemplate(template)
  restoreHeadingIds(template.content, headingIds)
  return template
}

/**
 * Parses and sanitizes article HTML without ever handing a raw string to an HTML
 * sink while Trusted Types is enforced. Strategy order:
 *  1. native Sanitizer `setHTML` (no sink at all) when the browser has it;
 *  2. the CSP-approved `app` policy, whose createHTML is the WASM sanitizer, so
 *     the sink receives TrustedHTML (formatting survives; ids are restored);
 *  3. plain `innerHTML` only when Trusted Types is not enforced.
 * Returns null when Trusted Types is enforced and no approved policy exists.
 */
function parseArticleTemplate(
  html: string,
  headingIds: readonly string[]
): HTMLTemplateElement | null {
  if (typeof document === "undefined") return null

  const native = createSafeTemplate()
  if (typeof native.setHTML === "function") {
    try {
      native.setHTML(html, { sanitizer: NATIVE_ARTICLE_SANITIZER })
      return finishTemplate(native, headingIds)
    } catch {
      // Fall through with a fresh template: a failed native parse must not leave partial nodes.
    }
  }

  const template = createSafeTemplate()
  if (!isTrustedTypesEnforced()) {
    template.innerHTML = html
    return finishTemplate(template, headingIds)
  }

  const policy = getAppTrustedTypesPolicy()
  if (!policy) return null
  try {
    const sink: { innerHTML: string | TrustedHTML } = template
    sink.innerHTML = policy.createHTML(html)
  } catch {
    return null
  }
  return finishTemplate(template, headingIds)
}

/**
 * Sanitized article nodes for insertion with DOM APIs (no HTML sink). Null when no
 * compliant parser exists, and always null during SSR.
 */
export function sanitizeArticleFragment(
  html: string,
  headingIds: readonly string[] = []
): DocumentFragment | null {
  return parseArticleTemplate(html, headingIds)?.content ?? null
}

const fragmentNodeToReact = (node: Node, key: string): ReactNode => {
  if (node.nodeType === Node.TEXT_NODE) return (node as Text).data
  if (node.nodeType !== Node.ELEMENT_NODE) return null

  const element = node as Element
  const tag = element.tagName.toLowerCase()
  if (!ALLOWED_TAGS.has(tag)) return null
  sanitizeElement(element)

  if (tag === "img" && !element.hasAttribute("src")) {
    return element.getAttribute("alt") ?? null
  }

  const props: Record<string, string | number> = {}
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    const value = attribute.value
    if (name === "class") {
      props.className = value
    } else if (name === "colspan" || name === "rowspan") {
      if (/^[1-9]\d{0,2}$/.test(value)) {
        props[name === "colspan" ? "colSpan" : "rowSpan"] = Number(value)
      }
    } else if (name === "width" || name === "height") {
      if (/^[1-9]\d{0,3}$/.test(value)) props[name] = Number(value)
    } else {
      props[name] = value
    }
  }

  const children = Array.from(element.childNodes).map((child, index) =>
    fragmentNodeToReact(child, `${key}-${index}`)
  )
  return createElement(tag, { ...props, key } as never, ...children)
}

/** Converts nodes after `sanitizeArticleFragment` has applied its element and attribute allowlists. */
export const articleFragmentToReactNodes = (fragment: DocumentFragment): ReactNode[] =>
  Array.from(fragment.childNodes).map((node, index) =>
    fragmentNodeToReact(node, `article-${index}`)
  )

export function sanitizeArticleHtml(html: string): string {
  if (typeof document === "undefined") {
    return htmlToPlainText(html)
  }

  const template = parseArticleTemplate(html, [])
  return template ? template.innerHTML : htmlToPlainText(html)
}
