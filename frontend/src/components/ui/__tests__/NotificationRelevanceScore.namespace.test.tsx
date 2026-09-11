import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const i18nMocks = vi.hoisted(() => ({
  useTranslation: vi.fn((namespace?: string) => ({
    t: (key: string) => key,
    namespace,
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: i18nMocks.useTranslation,
}))

import { NotificationRelevanceScore } from "@/components/ui/NotificationRelevanceScore"

describe("NotificationRelevanceScore translation namespace", () => {
  beforeEach(() => {
    i18nMocks.useTranslation.mockClear()
  })

  it("requests the common namespace directly for relevance labels", () => {
    render(<NotificationRelevanceScore relevance="high" />)

    expect(i18nMocks.useTranslation).toHaveBeenCalledWith("common")
    expect(screen.getByLabelText("common:notifications.relevance.high")).toBeInTheDocument()
  })
})
