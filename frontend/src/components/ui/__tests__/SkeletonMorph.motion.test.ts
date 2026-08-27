import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const microInteractionsCss = readFileSync(
  resolve(process.cwd(), "src/styles/partials/_micro-interactions.css"),
  "utf8"
)

const blockFor = (selector: string) => {
  const start = microInteractionsCss.indexOf(`${selector} {`)
  if (start < 0) return ""

  const bodyStart = microInteractionsCss.indexOf("{", start) + 1
  const bodyEnd = microInteractionsCss.indexOf("\n  }", bodyStart)
  return bodyEnd < 0 ? "" : microInteractionsCss.slice(bodyStart, bodyEnd)
}

describe("SkeletonMorph motion contract", () => {
  it("keeps loaded content compositor-safe with opacity-only motion", () => {
    const contentBlock = blockFor(".skeleton-morph-content")
    const loadedBlock = blockFor('.skeleton-morph-content[data-loaded="true"]')

    expect(contentBlock).toContain("opacity: 0")
    expect(contentBlock).toMatch(/transition:\s*opacity\b/)
    expect(contentBlock).not.toMatch(/\bfilter\b|blur\(/)
    expect(loadedBlock).toContain("opacity: 1")
    expect(loadedBlock).not.toMatch(/\bfilter\b|blur\(/)
  })
})
