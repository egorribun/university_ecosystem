import { JSDOM } from "jsdom"

const seoSelectors = [
  'meta[name="title"]',
  'meta[name="description"]',
  'meta[property="og:type"]',
  'meta[property="og:title"]',
  'meta[property="og:description"]',
  'meta[property="og:image"]',
  'meta[name="twitter:card"]',
  'meta[name="twitter:title"]',
  'meta[name="twitter:description"]',
  'meta[name="twitter:image"]',
]

export function normalizeMetadataText(value) {
  return value.normalize("NFC").replace(/\s+/gu, " ").trim()
}

export function extractSeoMetadata(markup) {
  if (markup === null) return null

  const head = new JSDOM(markup).window.document.head
  const content = (selector) => head.querySelector(selector)?.getAttribute("content") ?? null

  return {
    title: normalizeMetadataText(head.querySelector("title")?.textContent ?? ""),
    titleCount: head.querySelectorAll("title").length,
    metaTitle: content('meta[name="title"]'),
    description: content('meta[name="description"]'),
    descriptionCount: head.querySelectorAll('meta[name="description"]').length,
    ogType: content('meta[property="og:type"]'),
    ogTitle: content('meta[property="og:title"]'),
    ogDescription: content('meta[property="og:description"]'),
    ogImage: content('meta[property="og:image"]'),
    twitterCard: content('meta[name="twitter:card"]'),
    twitterTitle: content('meta[name="twitter:title"]'),
    twitterDescription: content('meta[name="twitter:description"]'),
    twitterImage: content('meta[name="twitter:image"]'),
    seoMetaCounts: Object.fromEntries(
      seoSelectors.map((selector) => [selector, head.querySelectorAll(selector).length])
    ),
  }
}

export function matchesRequestedCatalogTitle(language, catalogs, renderedTitle) {
  const requestedTranslation = catalogs[language]?.pageTitle
  if (typeof requestedTranslation !== "string" || requestedTranslation.trim() === "") return false
  const expectedTitle = requestedTranslation + " | University Ecosystem"
  return normalizeMetadataText(renderedTitle) === normalizeMetadataText(expectedTitle)
}
