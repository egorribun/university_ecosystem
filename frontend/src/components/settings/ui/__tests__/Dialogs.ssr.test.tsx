/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/hooks/useFocusTrap", () => ({ default: () => ({ current: null }) }))

import { Dialog } from "@/components/settings/ui/Dialogs"

describe("settings Dialog SSR", () => {
  it("renders nothing without a document", () => {
    expect(
      renderToString(
        <Dialog open onClose={vi.fn()}>
          Body
        </Dialog>
      )
    ).toBe("")
  })
})
