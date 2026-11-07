import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const stylesheet = readFileSync(new URL("../src/styles/tailwind.css", import.meta.url), "utf8")

test("Tailwind dark utilities honor the explicit theme class after all stylesheet imports", () => {
  const imports = [...stylesheet.matchAll(/^@import\s+[^;]+;/gmu)]
  const lastImportEnd = Math.max(...imports.map((match) => match.index + match[0].length))
  const themeRule = stylesheet.indexOf("@theme")
  const classVariantText = "@custom-variant dark (&:where(.dark, .dark *));"
  const classVariant = stylesheet.indexOf(classVariantText)

  assert.ok(imports.length > 0, "the stylesheet must retain its import prelude")
  assert.notEqual(themeRule, -1, "the Tailwind theme rule must exist")
  assert.ok(
    classVariant > lastImportEnd && classVariant < themeRule,
    "the dark variant must follow every import and precede the Tailwind theme rule"
  )
  assert.equal(
    stylesheet.match(/@custom-variant\s+dark\b/gu)?.length,
    1,
    "the Tailwind dark variant must be declared exactly once"
  )
})
