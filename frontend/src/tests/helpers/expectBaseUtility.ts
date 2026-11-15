import postcss, { type AnyNode } from "postcss"
import { expect } from "vitest"
import compiledCss from "@/styles/tailwind.css?inline"

const stylesheet = postcss.parse(compiledCss)

// JSDOM has no layout engine. Check the real compiled base utilities without
// pretending these declarations prove rendered geometry or breakpoint layout.
export function expectBaseUtility(element: HTMLElement, property: string, value: string) {
  const selectors = new Set(Array.from(element.classList, (name) => `.${CSS.escape(name)}`))
  const values: string[] = []
  stylesheet.walkRules((rule) => {
    if (!rule.selectors.some((selector) => selectors.has(selector))) return
    for (let parent: AnyNode | undefined = rule.parent; parent; parent = parent.parent) {
      if (parent.type === "atrule" && parent.name === "media") return
    }
    rule.walkDecls(property, (declaration) => {
      values.push(declaration.value)
    })
  })
  expect(values, `${element.tagName} base ${property}`).toContain(value)
}
