import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  buildLessonsByDay,
  getEndTimeStr,
  getTimeStr,
  GROUPS_STORAGE_TTL_MS,
  groupsStorageKey,
  type Lesson,
  readFromStorage,
  SCHEDULE_STORAGE_TTL_MS,
  scheduleStorageKey,
  STORAGE_SCHEMA_VERSION,
  writeToStorage,
} from "@/components/schedule/scheduleUtils"

// Fixed wall-clock so TTL math is deterministic.
const FIXED_NOW = new Date("2026-06-16T12:00:00.000Z")

const makeLesson = (overrides: Partial<Lesson> = {}): Lesson => ({
  id: "l1",
  weekday: "Monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  ...overrides,
})

beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers()
  vi.setSystemTime(FIXED_NOW)
})

afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
})

// ---------------------------------------------------------------------------
// readFromStorage / writeToStorage
// ---------------------------------------------------------------------------
describe("readFromStorage / writeToStorage", () => {
  it("keeps the storage contract keys and five-minute TTLs stable", () => {
    expect(groupsStorageKey).toBe("sched:groups")
    expect(scheduleStorageKey("group-42")).toBe("sched:group-42")
    expect(GROUPS_STORAGE_TTL_MS).toBe(300_000)
    expect(SCHEDULE_STORAGE_TTL_MS).toBe(300_000)
  })

  it("round-trips a value written by writeToStorage", () => {
    const key = scheduleStorageKey("g1")
    writeToStorage(key, { a: 1, b: "two" })

    const result = readFromStorage<{ a: number; b: string }>(key)
    expect(result).toEqual({ value: { a: 1, b: "two" }, timestamp: FIXED_NOW.getTime() })
  })

  it("returns undefined when the key is absent", () => {
    expect(readFromStorage(groupsStorageKey)).toBeUndefined()
  })

  it("returns undefined and removes entry on schema version mismatch", () => {
    const key = scheduleStorageKey("g2")
    localStorage.setItem(
      key,
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION + 1,
        timestamp: FIXED_NOW.getTime(),
        data: { stale: true },
      })
    )

    expect(readFromStorage(key)).toBeUndefined()
    expect(localStorage.getItem(key)).toBeNull()
  })

  it("respects a custom version option (matching custom version reads back)", () => {
    const key = scheduleStorageKey("g-custom")
    writeToStorage(key, "payload", { version: 9 })

    // Default version (1) sees a mismatch and removes it.
    expect(readFromStorage(key)).toBeUndefined()

    // Re-write and read with the matching custom version.
    writeToStorage(key, "payload", { version: 9 })
    expect(readFromStorage<string>(key, { version: 9 })).toEqual({
      value: "payload",
      timestamp: FIXED_NOW.getTime(),
    })
  })

  it("returns undefined and removes entry once TTL has expired", () => {
    const key = scheduleStorageKey("g3")
    writeToStorage(key, { fresh: false })

    // Advance just past the default TTL window.
    vi.setSystemTime(new Date(FIXED_NOW.getTime() + SCHEDULE_STORAGE_TTL_MS + 1))

    expect(readFromStorage(key)).toBeUndefined()
    expect(localStorage.getItem(key)).toBeNull()
  })

  it("returns the value while still inside the TTL window", () => {
    const key = scheduleStorageKey("g4")
    writeToStorage(key, { fresh: true })

    // Advance to exactly the TTL boundary (diff === maxAgeMs, not greater).
    vi.setSystemTime(new Date(FIXED_NOW.getTime() + SCHEDULE_STORAGE_TTL_MS))

    expect(readFromStorage<{ fresh: boolean }>(key)).toEqual({
      value: { fresh: true },
      timestamp: FIXED_NOW.getTime(),
    })
  })

  it("honors a custom maxAgeMs option", () => {
    const key = scheduleStorageKey("g5")
    writeToStorage(key, "v")

    vi.setSystemTime(new Date(FIXED_NOW.getTime() + 1000))
    // 1000ms elapsed, maxAge 500ms → expired.
    expect(readFromStorage<string>(key, { maxAgeMs: 500 })).toBeUndefined()
  })

  it("returns undefined and removes entry on NaN timestamp", () => {
    const key = scheduleStorageKey("g6")
    localStorage.setItem(
      key,
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        timestamp: "not-a-number",
        data: { x: 1 },
      })
    )

    expect(readFromStorage(key)).toBeUndefined()
    expect(localStorage.getItem(key)).toBeNull()
  })

  it("returns undefined and removes entry on a missing timestamp field", () => {
    const key = scheduleStorageKey("g7")
    localStorage.setItem(
      key,
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        data: { x: 1 },
      })
    )

    expect(readFromStorage(key)).toBeUndefined()
    expect(localStorage.getItem(key)).toBeNull()
  })

  it("returns undefined for a non-object stored payload without removing", () => {
    const key = scheduleStorageKey("g8")
    localStorage.setItem(key, JSON.stringify(42))

    expect(readFromStorage(key)).toBeUndefined()
    // Non-object short-circuits before any remove() call.
    expect(localStorage.getItem(key)).toBe("42")
  })

  it("returns undefined when version matches and ts is fresh but 'data' key is absent", () => {
    const key = scheduleStorageKey("g9")
    localStorage.setItem(
      key,
      JSON.stringify({
        version: STORAGE_SCHEMA_VERSION,
        timestamp: FIXED_NOW.getTime(),
      })
    )

    // Passes version + TTL guards, then fails the `"data" in parsed` check.
    expect(readFromStorage(key)).toBeUndefined()
    expect(localStorage.getItem(key)).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// extractHHMM via getTimeStr / getEndTimeStr
// ---------------------------------------------------------------------------
describe("getTimeStr / getEndTimeStr (extractHHMM regex)", () => {
  it("returns '' for null/undefined/empty time fields", () => {
    expect(getTimeStr(makeLesson({ start_time: null }))).toBe("")
    expect(getTimeStr(makeLesson({ start_time: "" }))).toBe("")
    expect(getEndTimeStr(makeLesson({ end_time: null }))).toBe("")
  })

  it("extracts HH:MM from a plain HH:MM string", () => {
    expect(getTimeStr(makeLesson({ start_time: "09:30" }))).toBe("09:30")
  })

  it("extracts the first HH:MM match from an ISO datetime", () => {
    expect(getTimeStr(makeLesson({ start_time: "2026-06-16T08:05:00Z" }))).toBe("08:05")
  })

  it("extracts HH:MM from an HH:MM:SS string", () => {
    expect(getEndTimeStr(makeLesson({ end_time: "14:45:00" }))).toBe("14:45")
  })

  it("returns '' when no HH:MM pattern exists (regex no-match branch)", () => {
    expect(getTimeStr(makeLesson({ start_time: "morning" }))).toBe("")
    // Single-digit-hour formats lack the required two-digit pair.
    expect(getTimeStr(makeLesson({ start_time: "9:30" }))).toBe("")
  })
})

// ---------------------------------------------------------------------------
// buildLessonsByDay
// ---------------------------------------------------------------------------
describe("buildLessonsByDay", () => {
  it("groups lessons by weekday and sorts each day by start time", () => {
    const schedule: Lesson[] = [
      makeLesson({ id: "m2", weekday: "Monday", start_time: "11:00" }),
      makeLesson({ id: "m1", weekday: "Monday", start_time: "09:00" }),
      makeLesson({ id: "t1", weekday: "Tuesday", start_time: "10:00" }),
    ]
    const result = buildLessonsByDay(schedule, ["Monday", "Tuesday"])

    expect([...result.keys()]).toEqual(["Monday", "Tuesday"])
    expect(result.get("Monday")?.map((l) => l.id)).toEqual(["m1", "m2"])
    expect(result.get("Tuesday")?.map((l) => l.id)).toEqual(["t1"])
  })

  it("creates an empty array entry for a weekday with no lessons", () => {
    const result = buildLessonsByDay([makeLesson({ weekday: "Monday" })], ["Monday", "Wednesday"])
    expect(result.get("Wednesday")).toEqual([])
  })

  it("returns an empty map when no weekdays are supplied", () => {
    const result = buildLessonsByDay([makeLesson()], [])
    expect(result.size).toBe(0)
  })
})
