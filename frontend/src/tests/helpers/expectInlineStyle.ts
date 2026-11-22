import { expect } from "vitest"

type InlineStyle = Readonly<Record<string, string>>

function inlineElement(element: Element | null | undefined): HTMLElement | SVGElement {
  if (!(element instanceof HTMLElement || element instanceof SVGElement)) {
    throw new Error("Expected an element with an inline style declaration")
  }
  return element
}

function cssPropertyName(property: string): string {
  return property.startsWith("--")
    ? property
    : property.replace(/[A-Z]/g, (letter) => "-" + letter.toLowerCase())
}

function normalizedDeclarations(
  element: HTMLElement | SVGElement,
  style: InlineStyle
): Array<[string, string]> {
  const entries = Object.entries(style)
  if (entries.length === 0) throw new Error("Expected at least one inline declaration")
  return entries.map(([key, value]) => {
    const property = cssPropertyName(key)
    // A fresh declaration per property keeps shorthands from merging with longhands.
    const expected = element.ownerDocument.createElement("div").style
    expected.setProperty(property, value)
    const normalized = expected.getPropertyValue(property)
    expect(normalized, `Expected ${property} must be valid, nonempty CSS`).not.toBe("")
    return [property, normalized]
  })
}

/**
 * Assert inline declarations as the CSSOM serializes them. Unlike `toHaveStyle`,
 * this does not read the computed style, so unresolved `var()` tokens stay visible
 * and equivalent spellings such as `translateY(0)` and `translateY(0px)` match.
 */
export function expectInlineStyle(element: Element | null | undefined, style: InlineStyle): void {
  const target = inlineElement(element)
  for (const [property, normalized] of normalizedDeclarations(target, style)) {
    expect(target.style.getPropertyValue(property), property).toBe(normalized)
  }
}

/** Assert that none of the given inline declarations is present with that value. */
export function expectInlineStyleAbsent(
  element: Element | null | undefined,
  style: InlineStyle
): void {
  const target = inlineElement(element)
  for (const [property, normalized] of normalizedDeclarations(target, style)) {
    expect(target.style.getPropertyValue(property), property).not.toBe(normalized)
  }
}
