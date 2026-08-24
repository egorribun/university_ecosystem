import { describe, expect, it } from "vitest"

import { applyOptimisticFileAction } from "@/components/events/helpers"

describe("applyOptimisticFileAction defensive fallback", () => {
  it("preserves files for an unknown runtime action", () => {
    const files = [{ id: "f-1", event_id: "e-1", file_url: "/one.pdf" }]

    expect(applyOptimisticFileAction(files, { type: "unknown" } as never)).toBe(files)
  })
})
