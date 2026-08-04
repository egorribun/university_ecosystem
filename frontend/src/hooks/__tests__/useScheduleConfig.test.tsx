/**
 * Session 11 coverage: src/hooks/useScheduleConfig.ts
 *
 * i18n-only hook (no MSW, no QueryClient). Tests drive it with controlled
 * createInstance() i18n instances via <I18nextProvider> so the parsed weekday /
 * lessonType structure is deterministic (we assert against our own resource,
 * exercising identical code paths to the real bundle). Broken-resource variants
 * cover the asRecord guards + every toConfig fallback branch + the
 * minimalWeekdayFallback / minimalLessonTypeFallback empty-config branches.
 */
import { renderHook } from "@testing-library/react"
import { createInstance, type i18n as I18nType } from "i18next"
import type { PropsWithChildren, ReactElement } from "react"
import { createElement } from "react"
import { I18nextProvider, initReactI18next } from "react-i18next"
import { describe, expect, it } from "vitest"

import {
  defaultLessonTypeColor,
  minimalLessonTypeFallback,
  minimalWeekdayFallback,
} from "@/components/schedule/scheduleUtils"
import { useScheduleConfig } from "../useScheduleConfig"

function makeI18n(schedule: Record<string, unknown>): I18nType {
  const inst = createInstance()
  // Inline resources + no backend → init resolves synchronously.
  void inst.use(initReactI18next).init({
    lng: "en",
    fallbackLng: false, // missing keys return the key string (so asRecord -> {})
    ns: ["schedule"],
    defaultNS: "schedule",
    resources: { en: { schedule } },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    keySeparator: ".",
  })
  return inst
}

function wrap(inst: I18nType) {
  const Wrapper = ({ children }: PropsWithChildren): ReactElement =>
    createElement(I18nextProvider, { i18n: inst }, children)
  Wrapper.displayName = "TestI18nWrapper"
  return Wrapper
}

const VALID = {
  weekdays: {
    order: ["mon", "tue", "wed", "thu", "fri", "sat"],
    items: {
      mon: { backend: ["Monday", "Понедельник"], long: "Monday", short: "Mon" },
      tue: { backend: ["Tuesday"], long: "Tuesday", short: "Tue" },
      wed: { backend: ["Wednesday"], long: "Wednesday", short: "Wed" },
      thu: { backend: ["Thursday"], long: "Thursday", short: "Thu" },
      fri: { backend: ["Friday"], long: "Friday", short: "Fri" },
      sat: { backend: ["Saturday"], long: "Saturday", short: "Sat" },
    },
  },
  lessonTypes: {
    order: ["lecture", "practice", "lab", "project"],
    items: {
      lecture: { backend: ["lecture", "Лекция"], label: "Lecture", color: "var(--badge-lec)" },
      practice: { backend: ["practice"], label: "Practical", color: "var(--badge-prac)" },
      lab: { backend: ["lab"], label: "Lab", color: "var(--badge-lab)" },
      project: { backend: ["project"], label: "Project", color: "var(--badge-proj)" },
    },
  },
}

function renderValid() {
  return renderHook(() => useScheduleConfig(), { wrapper: wrap(makeI18n(VALID)) })
}

describe("useScheduleConfig — weekday config (valid resource)", () => {
  it("builds weekdayConfigs from order + items", () => {
    const { result } = renderValid()
    expect(result.current.weekdayConfigs.map((c) => c.id)).toEqual([
      "mon",
      "tue",
      "wed",
      "thu",
      "fri",
      "sat",
    ])
    expect(result.current.weekdayConfigs[0]).toEqual({
      id: "mon",
      backend: ["Monday", "Понедельник"],
      long: "Monday",
      short: "Mon",
    })
  })

  it("derives weekdayBackend / weekdayLabels / weekdayShort", () => {
    const { result } = renderValid()
    expect(result.current.weekdayBackend).toEqual([
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
    ])
    expect(result.current.weekdayLabels[0]).toBe("Monday")
    expect(result.current.weekdayShort[0]).toBe("Mon")
    expect(result.current.weekdayLabels).toHaveLength(6)
  })

  it("getDayLabel resolves id, backend alias, and falls back to the value", () => {
    const { result } = renderValid()
    expect(result.current.getDayLabel("mon")).toBe("Monday")
    expect(result.current.getDayLabel("Понедельник")).toBe("Monday") // backend alias
    expect(result.current.getDayLabel("nonexistent-xyz")).toBe("nonexistent-xyz")
  })

  it("normalizeLessons rewrites weekday to the canonical backend (changed path)", () => {
    const { result } = renderValid()
    const input = [
      { id: "l1", weekday: "mon", parity: "both", start_time: null, end_time: null } as never,
    ]
    const out = result.current.normalizeLessons(input)
    expect(out).not.toBe(input) // new array
    expect((out[0] as { weekday: string }).weekday).toBe("Monday")
  })

  it("normalizeLessons returns the same array when already canonical (unchanged)", () => {
    const { result } = renderValid()
    const input = [
      { id: "l1", weekday: "Monday", parity: "both", start_time: null, end_time: null } as never,
    ]
    expect(result.current.normalizeLessons(input)).toBe(input)
  })

  it("normalizeLessons leaves non-string weekday + null elements untouched", () => {
    const { result } = renderValid()
    const input = [
      { id: "l", weekday: 123, parity: "both", start_time: null, end_time: null } as never,
      null as never,
    ]
    expect(result.current.normalizeLessons(input)).toBe(input)
  })

  it("normalizeLessons returns same array for unknown weekday (no canonical)", () => {
    const { result } = renderValid()
    const input = [
      { id: "l", weekday: "zzz", parity: "both", start_time: null, end_time: null } as never,
    ]
    expect(result.current.normalizeLessons(input)).toBe(input)
  })
})

describe("useScheduleConfig — lesson type config (valid resource)", () => {
  it("builds lessonTypeConfigs + labels + options + default", () => {
    const { result } = renderValid()
    expect(result.current.lessonTypeConfigs.map((c) => c.id)).toEqual([
      "lecture",
      "practice",
      "lab",
      "project",
    ])
    expect(result.current.lessonTypeConfigs[0]!.color).toBe("var(--badge-lec)")
    expect(result.current.lessonTypeLabels.get("lecture")).toBe("Lecture")
    expect(result.current.lessonTypeLabels.get("Лекция")).toBe("Lecture") // backend alias
    expect(result.current.lessonTypeLabels.get("nope")).toBeUndefined()
    expect(result.current.lessonTypeOptions[0]).toEqual({ value: "lecture", label: "Lecture" })
    expect(result.current.defaultLessonType).toBe("lecture")
  })

  it("getLessonTypeColor: id hit, backend hit, null + unknown fall back", () => {
    const { result } = renderValid()
    expect(result.current.getLessonTypeColor("lecture")).toBe("var(--badge-lec)")
    expect(result.current.getLessonTypeColor("Лекция")).toBe("var(--badge-lec)")
    expect(result.current.getLessonTypeColor(null)).toBe(defaultLessonTypeColor)
    expect(result.current.getLessonTypeColor("unknown")).toBe(defaultLessonTypeColor)
  })

  it("toBackendLessonType: id -> backend[0], null -> '', unknown -> value", () => {
    const { result } = renderValid()
    expect(result.current.toBackendLessonType("lecture")).toBe("lecture")
    expect(result.current.toBackendLessonType(null)).toBe("")
    expect(result.current.toBackendLessonType("not-an-id")).toBe("not-an-id")
  })
})

describe("useScheduleConfig — fallback branches (broken resources)", () => {
  it("weekdays.items array -> asRecord {} + empty order -> minimalWeekdayFallback", () => {
    const inst = makeI18n({ weekdays: { items: [], order: [] } })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs).toEqual(minimalWeekdayFallback)
  })

  it("lessonTypes primitives -> asRecord {} + empty -> [minimalLessonTypeFallback]", () => {
    const inst = makeI18n({ lessonTypes: { items: 42, order: 99 } })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.lessonTypeConfigs).toEqual([minimalLessonTypeFallback])
    expect(result.current.defaultLessonType).toBe("lesson")
  })

  it("weekdays.order not array -> uses Object.keys(items)", () => {
    const inst = makeI18n({
      weekdays: { items: { foo: { backend: ["F"], long: "Foo", short: "Fo" } } },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs[0]!.id).toBe("foo")
    expect(result.current.weekdayConfigs[0]!.long).toBe("Foo")
  })

  it("toConfig: entry undefined + no fallback-by-id -> inline id fallback", () => {
    const inst = makeI18n({ weekdays: { order: ["xyz"], items: {} } })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs[0]).toEqual({
      id: "xyz",
      backend: ["xyz"],
      long: "xyz",
      short: "xyz",
    })
  })

  it("toConfig: backend as a single string -> wrapped in array", () => {
    const inst = makeI18n({
      weekdays: { order: ["d1"], items: { d1: { backend: "SoloBackend", long: "L", short: "S" } } },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs[0]!.backend).toEqual(["SoloBackend"])
  })

  it("toConfig second loop appends items not present in order", () => {
    const inst = makeI18n({
      weekdays: {
        order: ["a"],
        items: {
          a: { backend: ["A"], long: "AA", short: "A" },
          b: { backend: ["B"], long: "BB", short: "B" },
        },
      },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs.map((c) => c.id)).toEqual(["a", "b"])
  })

  it("uses the fallback identity when a configured backend list is empty", () => {
    const inst = makeI18n({
      weekdays: { order: ["empty"], items: { empty: { backend: [], long: "Empty", short: "E" } } },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.weekdayConfigs[0]!.backend).toEqual(["empty"])
  })

  it("lessonType toConfig: backend-string + label/color fallbacks", () => {
    const inst = makeI18n({
      lessonTypes: { order: ["q"], items: { q: { backend: "single" } } },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.lessonTypeConfigs[0]).toEqual({
      id: "q",
      backend: ["single"],
      label: "q",
      color: defaultLessonTypeColor,
    })
  })

  it("lessonType toConfig uses an inline fallback for a missing ordered entry", () => {
    const inst = makeI18n({ lessonTypes: { order: ["missing"], items: {} } })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.lessonTypeConfigs[0]).toEqual({
      id: "missing",
      backend: ["missing"],
      label: "missing",
      color: defaultLessonTypeColor,
    })
  })

  it("appends lesson types that are absent from the configured order", () => {
    const inst = makeI18n({
      lessonTypes: {
        order: ["first"],
        items: {
          first: { backend: ["first"], label: "First" },
          extra: { backend: ["extra"], label: "Extra" },
        },
      },
    })
    const { result } = renderHook(() => useScheduleConfig(), { wrapper: wrap(inst) })
    expect(result.current.lessonTypeConfigs.map((config) => config.id)).toEqual(["first", "extra"])
  })
})
