import { describe, expect, it } from "vitest"

import * as feedback from "@/components/feedback"
import * as media from "@/components/media"
import * as motion from "@/components/motion"
import * as pwa from "@/components/pwa"
import * as search from "@/components/search"
import * as eventTypes from "@/features/events/types"
import * as map from "@/features/map"
import * as settings from "@/pages/settings/index"

describe("public barrel export contracts", () => {
  it.each([
    ["feedback", feedback],
    ["media", media],
    ["motion", motion],
    ["pwa", pwa],
    ["search", search],
    ["map", map],
    ["settings", settings],
  ])("loads every runtime export from %s", (_name, exports) => {
    const values = Object.values(exports)

    expect(values.length).toBeGreaterThan(0)
    expect(values.every((value) => value !== undefined)).toBe(true)
  })

  it("publishes a complete immutable event-form template", () => {
    expect(eventTypes.initialEventFormState).toEqual({
      title: "",
      description: "",
      title_en: "",
      description_en: "",
      event_type: "",
      event_type_en: "",
      location: "",
      location_en: "",
      speaker: "",
      starts_at: "",
      ends_at: "",
    })
  })
})
