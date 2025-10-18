import { describe, it, expect, beforeEach } from "vitest"

import { getPersistedTopics, setPersistedTopics } from "../subscribe"

const PROFILE_CACHE_KEY = "ecosystem.profile.cache.v1"
const TOPICS_KEY = "push:last_topics"

const setActiveUser = (id: string | number | null) => {
  if (typeof localStorage === "undefined") return
  if (id == null) {
    localStorage.removeItem(PROFILE_CACHE_KEY)
    return
  }

  localStorage.setItem(
    PROFILE_CACHE_KEY,
    JSON.stringify({ data: { id }, savedAt: new Date().toISOString() })
  )
}

const readTopicsStorage = () => {
  const raw = localStorage.getItem(TOPICS_KEY)
  return raw ? JSON.parse(raw) : null
}

describe("push topic persistence", () => {
  beforeEach(() => {
    localStorage.clear()
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
