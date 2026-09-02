import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const useTranslationMock = vi.hoisted(() => vi.fn())

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))

import { MapHeader } from "@/components/map/MapHeader"

describe("MapHeader mutation contracts", () => {
  it("uses the map namespace and preserves the title badge styling and copy", () => {
    useTranslationMock.mockReturnValue({ t: (key: string) => `translated:${key}` })

    render(<MapHeader />)

    expect(useTranslationMock).toHaveBeenCalledWith("map")
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "translated:page.titletranslated:page.badge"
    )
    const badge = screen.getByText("translated:page.badge")
    expect(badge).toHaveClass("map-badge-matte", "rounded-full", "px-2", "py-0.5")
    expect((badge as HTMLElement).style.fontSize).toBe("0.45em")
  })
})
