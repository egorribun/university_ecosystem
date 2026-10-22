import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const source = readFileSync(
  resolve(process.cwd(), "tests/e2e/events-history-scroll-restoration.spec.ts"),
  "utf8"
)

describe("events history scroll-restoration acceptance contract", () => {
  it("checks the same event identity and viewport position after Back", () => {
    expect(source).toMatch(
      /const selectedEventHref = \(await selectedEvent\.getAttribute\("href"\)\) \?\? ""/u
    )
    expect(source).toMatch(
      /expect\(selectedEventHref\)\.toMatch\(\/\^\\\/events\\\/uuid-\\d\+\$\/u\)/u
    )
    expect(source).toMatch(
      /const selectedEventUrl = new URL\(selectedEventHref, page\.url\(\)\)\.href/u
    )
    expect(source).toMatch(/await expect\(page\)\.toHaveURL\(selectedEventUrl\)/u)
    expect(source).toMatch(
      /const restoredEvent = page\.locator\("\.events-card-title a"\)\.nth\(8\)/u
    )
    expect(source).toMatch(
      /await expect\(restoredEvent\)\.toHaveAttribute\(\s*"href",\s*selectedEventHref\s*\)/u
    )
    expect(source).toMatch(/toBe\(originalPosition\.scrollY\)/u)
    expect(source).toMatch(/Math\.abs\(restoredPosition - originalPosition\.top\)/u)
  })
})
