import { describe, it, expect, afterEach } from "vitest"

import { setEventsHeroId, getEventsHeroId, clearEventsHeroId } from "../eventsTransition"
import { setNewsHeroId, getNewsHeroId, clearNewsHeroId } from "../newsTransition"
import {
  setScheduleTransitionId,
  getScheduleTransitionId,
  clearScheduleTransition,
} from "../scheduleTransition"

// These tiny stores hold module-level `let` state, so clear after each test.
afterEach(() => {
  clearEventsHeroId()
  clearNewsHeroId()
  clearScheduleTransition()
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

describe("scheduleTransition", () => {
  it("set → get → clear → null", () => {
    expect(getScheduleTransitionId()).toBeNull()
    setScheduleTransitionId("lesson-1")
    expect(getScheduleTransitionId()).toBe("lesson-1")
    clearScheduleTransition()
    expect(getScheduleTransitionId()).toBeNull()
  })
})
