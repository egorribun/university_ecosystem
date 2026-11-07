import { JSDOM } from "jsdom"

// A missing requested resource can resolve to a normal-looking string from
// the fallback locale, so compare the rendered landmark to that exact resource.
export function matchesNewsSearchLocale(markup, expected) {
  if (markup === null || typeof expected !== "string" || expected.trim() === "") return false
  const root = new JSDOM(markup).window.document.querySelector("#root")
  if (!root) return false
  const inputs = root.querySelectorAll(".news-theme header input[placeholder]")
  if (inputs.length !== 1) return false
  const input = inputs[0]
  return (
    input.getAttribute("placeholder") === expected && input.getAttribute("aria-label") === expected
  )
}
