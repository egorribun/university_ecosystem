import { describe, it, expect } from "vitest"

import * as hooks from "@/hooks"

/**
 * Barrel smoke test — importing `@/hooks` executes every re-export line, which
 * pulls in each top-level shared hook module. The assertions below spot-check a
 * representative slice (incl. all four `export { default as ... }` re-exports)
 * so the test fails loudly if a re-export goes stale, while the `import *`
 * itself credits the barrel's export statements.
 */
describe("hooks barrel (@/hooks)", () => {
  it("re-exports the four default-exported hooks as functions", () => {
    expect(typeof hooks.useActivityData).toBe("function")
    expect(typeof hooks.useFocusTrap).toBe("function")
    expect(typeof hooks.useMediaQuery).toBe("function")
    expect(typeof hooks.useScrollRestoration).toBe("function")
  })

  it("re-exports a representative slice of named hooks as functions", () => {
    const named = [
      "useDebounced",
      "useURLState",
      "useClock",
      "useSwipe",
      "useBookmarks",
      "useShare",
      "useTilt",
      "useSeason",
      "useTimeOfDay",
      "useWeather",
      "useLocalStorage",
      "useOnlineStatus",
      "useScheduleData",
      "useScheduleKeyboardNav",
      "useNextLesson",
      "useMapEvents",
      "useMapWeather",
    ] as const
    for (const name of named) {
      expect(typeof (hooks as Record<string, unknown>)[name]).toBe("function")
    }
  })
})
