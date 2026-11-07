import { JSDOM } from "jsdom"

// A missing resource may resolve to ordinary text from the fallback locale.
// Compare this always-rendered layout landmark to the requested catalog value.
export function matchesMainSkipLinkLocale(markup, expected) {
  if (markup === null || typeof expected !== "string" || expected.trim() === "") return false
  const root = new JSDOM(markup).window.document.querySelector("#root")
  if (!root) return false
  const links = root.querySelectorAll('a.skip-link[href="#main-content"]')
  return links.length === 1 && links[0].textContent === expected
}
