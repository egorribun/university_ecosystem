import { expect } from "vitest"

/** Assert an inline token declaration, not a theme-resolved computed color. */
export function expectInlineBackground(
  element: Element | null | undefined,
  value: string,
  property: "background" | "background-color" = "background"
): void {
  if (!(element instanceof HTMLElement || element instanceof SVGElement)) {
    throw new Error("Expected an element with an inline style declaration")
  }

  const expected = element.ownerDocument.createElement("div").style
  expected.setProperty(property, value)
  const normalized = expected.getPropertyValue(property)
  expect(normalized, "Expected background must be valid, nonempty CSS").not.toBe("")
  expect(element.style.getPropertyValue(property)).toBe(normalized)
}
