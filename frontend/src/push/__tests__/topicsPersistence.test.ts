import { describe, it, expect, beforeEach, vi } from "vitest"

import { getPersistedTopics, setPersistedTopics } from "../subscribe"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"

const TOPICS_KEY = "push:last_topics"

vi.mock("@/push/subscribe", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/push/subscribe")>()
  return {
    ...actual,
    getPersistedTopics: vi.fn().mockImplementation((options) => actual.getPersistedTopics(options)),
    setPersistedTopics: vi
      .fn()
      .mockImplementation((topics, options) => actual.setPersistedTopics(topics, options)),
  }
})
// The active topic namespace follows the confirmed authenticated identity.
const setActiveUser = (id: string | number | null) => {
  useAuthStore.setState({
    user: id == null ? null : ({ id } as unknown as UserState),
    loading: false,
  })
}

const readTopicsStorage = () => {
  const raw = localStorage.getItem(TOPICS_KEY)
  return raw ? JSON.parse(raw) : null
}

describe("push topic persistence", () => {
  beforeEach(() => {
    localStorage.clear()
    setActiveUser(null)
  })

  it("returns undefined when nothing is stored", () => {
    expect(getPersistedTopics()).toBeUndefined()
  })

  it("reads legacy shared topics", () => {
    localStorage.setItem(TOPICS_KEY, JSON.stringify(["system", "news"]))
    const topics = getPersistedTopics()
    expect(topics).toEqual(["news", "system"])
  })

  it("stores and reads topics for the active user", () => {
    setActiveUser(42)
    setPersistedTopics(["schedule", "news"])

    const raw = readTopicsStorage()
    expect(raw).not.toBeNull()
    expect(raw.version).toBe(2)
    expect(raw.perUser).toBeDefined()
    expect(raw.perUser["42"]).toEqual(["news", "schedule"])

    expect(getPersistedTopics()).toEqual(["news", "schedule"])
  })

  it("keeps selections isolated between different users", () => {
    setActiveUser(1)
    setPersistedTopics(["schedule"])

    setActiveUser(2)
    setPersistedTopics(["events"])

    setActiveUser(1)
    expect(getPersistedTopics()).toEqual(["schedule"])

    setActiveUser(2)
    expect(getPersistedTopics()).toEqual(["events"])
  })

  it("removes only the active user's topics when cleared", () => {
    setActiveUser(1)
    setPersistedTopics(["schedule"])
    setActiveUser(2)
    setPersistedTopics(["events"])

    setActiveUser(1)
    setPersistedTopics(null)

    setActiveUser(2)
    expect(getPersistedTopics()).toEqual(["events"])

    setActiveUser(1)
    expect(getPersistedTopics()).toBeUndefined()

    const raw = readTopicsStorage()
    expect(raw?.perUser).toBeDefined()
    expect(Object.keys(raw?.perUser ?? {})).toEqual(["2"])
  })

  it("reads stored topics for a specific user even when none is active", () => {
    setActiveUser(5)
    setPersistedTopics(["system"])

    setActiveUser(null)

    expect(getPersistedTopics({ userId: 5 })).toEqual(["system"])
  })

  it("stores shared topics when user is unknown", () => {
    setActiveUser(null)
    setPersistedTopics(["system"])

    const raw = readTopicsStorage()
    expect(raw).not.toBeNull()
    expect(raw.shared).toEqual(["system"])
    expect(getPersistedTopics()).toEqual(["system"])
  })

  it("migrates legacy shared topics when saving for a user", () => {
    localStorage.setItem(TOPICS_KEY, JSON.stringify(["events"]))
    setActiveUser(7)
    setPersistedTopics(["news"])

    const raw = readTopicsStorage()
    expect(raw).not.toBeNull()
    expect(raw.version).toBe(2)
    expect(raw.shared).toEqual(["events"])
    expect(raw.perUser["7"]).toEqual(["news"])
  })
})
