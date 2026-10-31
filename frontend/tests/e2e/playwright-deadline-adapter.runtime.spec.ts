import { expect, test } from "@playwright/test"

import { readPlaywrightTestSlotDeadlineAtMs } from "../../scripts/live-registration-admission.mjs"

test("reads the active deadline from the installed runner", ({ baseURL: _baseURL }, testInfo) => {
  const deadline = readPlaywrightTestSlotDeadlineAtMs(testInfo)
  expect(deadline).not.toBeNull()
  if (deadline === null) throw new Error("The Playwright deadline adapter failed closed")

  expect(Number.isFinite(deadline)).toBe(true)
  const remaining = deadline - performance.now()
  expect(remaining).toBeGreaterThan(0)
  expect(remaining).toBeLessThanOrEqual(testInfo.timeout)
})
