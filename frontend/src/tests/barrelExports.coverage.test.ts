import { describe, expect, it } from "vitest"

import * as eventTypes from "@/features/events/types"
import * as settings from "@/pages/settings/index"

describe("remaining settings entry point", () => {
  it("exports the settings appearance section", () => {
    expect(settings.AppearanceSection).toBeDefined()
  })

  it("provides the complete initial event-form state", () => {
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
