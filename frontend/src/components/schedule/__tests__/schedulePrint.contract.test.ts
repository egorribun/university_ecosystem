import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const scheduleCss = readFileSync(resolve(process.cwd(), "src/styles/tokens/schedule.css"), "utf8")
const printStart = scheduleCss.indexOf("@media print {")
const reducedMotionStart = scheduleCss.indexOf("/* ═", printStart)
const printCss = scheduleCss.slice(printStart, reducedMotionStart)
const rules = Array.from(printCss.matchAll(/([^{}]+)\{([^{}]*)\}/g))

describe("schedule print CSS", () => {
  it("keeps the current lesson card while suppressing only its decorative glow", () => {
    const lessonCardHideRule = rules.some(
      ([_, selector, declarations]) =>
        selector
          ?.split(",")
          .some((part) => part.trim() === ".schedule-theme.schedule-theme .sched-current-glow") &&
        /display:\s*none/.test(declarations ?? "")
    )
    expect(lessonCardHideRule).toBe(false)

    const lessonCardRule = rules.find(
      ([, selector]) => selector?.trim() === ".schedule-theme.schedule-theme .sched-current-glow"
    )?.[2]
    expect(lessonCardRule).toMatch(/animation:\s*none/)
    expect(lessonCardRule).toMatch(/box-shadow:\s*none/)

    const glowRule = rules.find(
      ([, selector]) =>
        selector?.trim() === ".schedule-theme.schedule-theme .sched-current-glow::after"
    )?.[2]
    expect(glowRule).toMatch(/display:\s*none/)
  })
})
