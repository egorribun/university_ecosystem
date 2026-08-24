/** @vitest-environment node */

import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { OfflineIndicator } from "@/components/feedback/OfflineIndicator"

describe("OfflineIndicator SSR", () => {
  it("renders nothing when the document is unavailable", () => {
    expect(renderToString(<OfflineIndicator />)).toBe("")
  })
})
