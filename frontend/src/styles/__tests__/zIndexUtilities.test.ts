import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const read = (path: string): string =>
  readFileSync(resolve(process.cwd(), path), "utf8").replace(/\r\n/gu, "\n")

const tailwind = read("src/styles/tailwind.css")
const primitives = read("src/styles/tokens/primitives.css")
const notificationsBell = read("src/components/feedback/NotificationsBell.tsx")

const layers = new Map(
  [...primitives.matchAll(/--z-([a-z]+): (-?\d+);/gu)].map(([, name, value]) => [
    name,
    Number(value),
  ])
)

describe("z-index layer utilities", () => {
  it("emits the popover layer so fixed popovers stay above page content", () => {
    // Without the utility the class compiled to nothing and the phone
    // notifications panel sat under footer content (z-surface).
    expect(tailwind).toContain("@utility z-popover {\n  z-index: var(--z-popover);\n}")
    expect(layers.get("popover")).toBe(1200)
    expect(notificationsBell).toContain('"fixed z-popover origin-top-right"')
  })

  it("keeps the popover layer above page surfaces and below modal dialogs", () => {
    const popover = layers.get("popover") ?? Number.NaN
    expect(popover).toBeGreaterThan(layers.get("surface") ?? Number.POSITIVE_INFINITY)
    expect(popover).toBeGreaterThan(layers.get("dropdown") ?? Number.POSITIVE_INFINITY)
    expect(popover).toBeLessThan(layers.get("modal") ?? Number.NEGATIVE_INFINITY)
  })
})
