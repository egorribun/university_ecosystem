import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, it, expect, vi } from "vitest"

const mocks = vi.hoisted(() => {
  const translationCalls: Array<{ key: string; options?: Record<string, unknown> }> = []
  const useTranslation = vi.fn(() => ({
    t: (key: string, options?: Record<string, unknown>) => {
      translationCalls.push({ key, options })
      return key
    },
    i18n: { language: mocks.language, changeLanguage: () => Promise.resolve() },
  }))

  return {
    language: "en",
    popupOnClose: undefined as (() => void) | undefined,
    popupProps: [] as Array<Record<string, unknown>>,
    linkProps: undefined as { to?: unknown; params?: unknown } | undefined,
    translationCalls,
    useTranslation,
    logError: vi.fn(),
  }
})

vi.mock("react-map-gl/maplibre", async () => {
  const { createElement } = await import("react")
  const base = (await import("@/tests/helpers/mapGlMock")).mapGlMock()
  return {
    ...base,
    Popup: ({
      children,
      onClose,
      ...props
    }: { children?: unknown; onClose?: () => void } & Record<string, unknown>) => {
      mocks.popupOnClose = onClose
      mocks.popupProps.push(props)
      return createElement("div", null, children as never)
    },
  }
})
vi.mock("react-i18next", () => ({
  useTranslation: mocks.useTranslation,
}))
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
    ...rest
  }: { children?: unknown; to?: unknown; params?: unknown } & Record<string, unknown>) => {
    mocks.linkProps = { to, params }
    return createElement(
      "a",
      { href: typeof to === "string" ? to : "#", ...rest },
      children as never
    )
  },
}))

import { EventMarker } from "@/components/map/EventMarker"
import type { MapEvent } from "@/hooks/useMapEvents"

const EVENT = {
  id: "e1",
  title: "Hackathon 2026",
  startsAt: "2026-06-15T18:00:00Z",
  location: "ГУК-305",
  geoCoords: [55.71, 37.81],
  participantCount: 12,
} as unknown as MapEvent

const baseProps = { event: EVENT }

const formatExpectedDate = (isoString: string, locale: string) =>
  new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }).format(new Date(isoString))

describe("EventMarker", () => {
  beforeEach(() => {
    mocks.language = "en"
    mocks.popupOnClose = undefined
    mocks.popupProps.length = 0
    mocks.linkProps = undefined
    mocks.translationCalls.length = 0
    mocks.useTranslation.mockClear()
    mocks.logError.mockReset()
  })

  it("renders the event pin with an accessible label", () => {
    render(<EventMarker {...baseProps} />)
    const pin = screen.getByRole("button", { name: "events.markerLabel" })
    expect(pin).toHaveStyle({
      minWidth: "44px",
      minHeight: "44px",
    })
    expect(pin.querySelector("path")).toHaveAttribute("fill", "#f59e0b")
    expect(mocks.useTranslation).toHaveBeenCalledWith("map")
    expect(mocks.translationCalls.find(({ key }) => key === "events.markerLabel")?.options).toEqual(
      {
        title: EVENT.title,
        date: formatExpectedDate(EVENT.startsAt, "en"),
      }
    )
  })

  it("fires onPopupOpen when the pin is clicked", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)
    await user.click(screen.getByRole("button", { name: "events.markerLabel" }))
    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it.each(["Enter", " "])("opens the popup from the %j keyboard key", async (key) => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)

    const marker = screen.getByRole("button", { name: "events.markerLabel" })
    marker.focus()
    await user.keyboard(key === " " ? "[Space]" : `{${key}}`)

    expect(onPopupOpen).toHaveBeenCalledOnce()
  })

  it("ignores unrelated keyboard keys", async () => {
    const user = userEvent.setup()
    const onPopupOpen = vi.fn()
    render(<EventMarker {...baseProps} onPopupOpen={onPopupOpen} />)

    screen.getByRole("button", { name: "events.markerLabel" }).focus()
    await user.keyboard("a")
    expect(onPopupOpen).not.toHaveBeenCalled()
  })

  it("renders the popup with the event title and a details link when open", () => {
    render(<EventMarker {...baseProps} isPopupOpen />)
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /events\.viewDetails/ })).toBeInTheDocument()
    expect(screen.getByText("events.participants")).toBeInTheDocument()
    expect(
      mocks.translationCalls.find(({ key }) => key === "events.participants")?.options
    ).toEqual({ count: EVENT.participantCount })
    expect(mocks.linkProps).toEqual({ to: "/events/$id", params: { id: EVENT.id } })
    expect(mocks.popupProps[0]).toMatchObject({
      closeButton: true,
      closeOnClick: false,
      className: "map-popup-premium",
      maxWidth: "260px",
    })
    expect(document.querySelector(".map-popup-card--compact .rounded-full")).toHaveStyle({
      backgroundColor: "#f59e0b",
    })
  })

  it.each([
    ["zero", 0],
    ["missing", undefined],
    ["null", null],
    ["non-numeric", "12"],
  ])("does not render a participant label for %s counts", (_label, participantCount) => {
    const event = { ...EVENT, participantCount } as unknown as MapEvent
    render(<EventMarker event={event} isPopupOpen />)
    expect(screen.queryByText("events.participants")).not.toBeInTheDocument()
  })

  it("recomputes the formatted date when the event timestamp changes", () => {
    const nextStartsAt = "2026-06-20T09:15:00Z"
    const initialDate = formatExpectedDate(EVENT.startsAt, "en")
    const nextDate = formatExpectedDate(nextStartsAt, "en")
    const { rerender } = render(<EventMarker {...baseProps} isPopupOpen />)

    expect(screen.getByText(initialDate)).toBeInTheDocument()
    rerender(<EventMarker event={{ ...EVENT, startsAt: nextStartsAt }} isPopupOpen />)
    expect(screen.getByText(nextDate)).toBeInTheDocument()
    expect(screen.queryByText(initialDate)).not.toBeInTheDocument()
  })

  it("forwards popup closure to the owner", () => {
    const onPopupClose = vi.fn()
    render(<EventMarker {...baseProps} isPopupOpen onPopupClose={onPopupClose} />)

    mocks.popupOnClose?.()
    expect(onPopupClose).toHaveBeenCalledOnce()
  })

  it("falls back to the source timestamp when date formatting fails", () => {
    mocks.language = "not_a_locale"
    render(<EventMarker {...baseProps} />)

    expect(mocks.logError).toHaveBeenCalledOnce()
  })
})
