import { describe, it, expect, afterEach } from "vitest"

import { setEventsHeroId, getEventsHeroId, clearEventsHeroId } from "../eventsTransition"
import { setNewsHeroId, getNewsHeroId, clearNewsHeroId } from "../newsTransition"

// These tiny stores hold module-level `let` state, so clear after each test.
afterEach(() => {
  clearEventsHeroId()
  clearNewsHeroId()
})

describe("eventsTransition", () => {
  it("set → get → clear → null", () => {
    expect(getEventsHeroId()).toBeNull()
    setEventsHeroId("event-1")
    expect(getEventsHeroId()).toBe("event-1")
    clearEventsHeroId()
    expect(getEventsHeroId()).toBeNull()
  })
})

describe("newsTransition", () => {
  it("set → get → clear → null", () => {
    expect(getNewsHeroId()).toBeNull()
    setNewsHeroId("news-1")
    expect(getNewsHeroId()).toBe("news-1")
    clearNewsHeroId()
    expect(getNewsHeroId()).toBeNull()
  })
})
