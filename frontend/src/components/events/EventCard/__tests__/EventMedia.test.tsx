import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
const { useTranslationMock, translationMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
  }
})

vi.mock("react-i18next", () => ({ useTranslation: useTranslationMock }))

import { EventMedia, invokeImageClick } from "@/components/events/EventCard/EventMedia"

const baseProps = {
  imageUrl: "https://picsum.photos/seed/ue-event/640/360",
  alt: "Event banner",
  eventType: "Workshop",
  timeStatus: { status: "none" as const },
  isReady: true,
  onReady: vi.fn(),
  onImageClick: vi.fn(),
}

describe("EventMedia", () => {
  it("ignores an absent image action callback", () => {
    const callback = vi.fn()

    invokeImageClick(undefined)
    invokeImageClick(callback)

    expect(callback).toHaveBeenCalledOnce()
  })

  it("renders the image button and the event type badge", () => {
    const { container } = render(<EventMedia {...baseProps} />)
    expect(screen.getByText("Workshop")).toBeInTheDocument()
    const button = screen.getByRole("button")
    expect(button).toBeEnabled()
    expect(button).toHaveClass("block", "h-full", "w-full")
    expect(screen.getByRole("img")).toHaveAttribute("draggable", "false")
    const frame = container.querySelector(".aspect-video")
    expect(frame).toHaveClass(
      "relative",
      "w-full",
      "overflow-hidden",
      "rounded-lg",
      "aspect-video",
      "max-h-50",
      "bg-linear-to-br",
      "from-event-media-tint-from",
      "to-event-media-tint-to",
      "border",
      "border-event-media-border"
    )
    expect(container.querySelector(".bg-linear-to-t")).toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
  })

  it("shows the live status indicator", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "live" }} />)
    expect(screen.getByText("common:statuses.live")).toBeInTheDocument()
  })

  it("shows the soon status indicator with the countdown text", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "soon", timeText: "15m" }} />)
    expect(screen.getByText(/events:card.statuses.in/)).toBeInTheDocument()
    expect(translationMock).toHaveBeenCalledWith("events:card.statuses.in", { time: "15m" })
  })

  it("does not render a status indicator for a neutral event", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "none" }} />)

    expect(screen.queryByText("common:statuses.live")).not.toBeInTheDocument()
    expect(screen.queryByText(/events:card.statuses.in/)).not.toBeInTheDocument()
  })

  it("does not render the soon indicator when a neutral event has stale countdown text", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "none", timeText: "15m" }} />)

    expect(screen.queryByText(/events:card.statuses.in/)).not.toBeInTheDocument()
  })

  it("fires onImageClick when the image is clicked", async () => {
    const user = userEvent.setup()
    const onImageClick = vi.fn()
    render(<EventMedia {...baseProps} onImageClick={onImageClick} />)
    await user.click(screen.getByRole("button"))
    expect(onImageClick).toHaveBeenCalledOnce()
  })

  it("uses the translated image alt text when no alt is provided", () => {
    render(<EventMedia {...baseProps} alt="" />)
    expect(screen.getByRole("img", { name: "events:alt.image" })).toBeInTheDocument()
  })

  it("shows the loading overlay until the image is ready", () => {
    const { container } = render(<EventMedia {...baseProps} isReady={false} />)
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument()
  })

  it("disables the image action and does not invoke a missing callback", async () => {
    const user = userEvent.setup()
    render(<EventMedia {...baseProps} onImageClick={undefined} />)
    const button = screen.getByRole("button")

    expect(button).toBeDisabled()
    await user.click(button)
    expect(baseProps.onImageClick).not.toHaveBeenCalled()
  })

  it("omits the type badge when eventType is empty", () => {
    const { container } = render(<EventMedia {...baseProps} eventType="" />)
    expect(screen.queryByText("Workshop")).not.toBeInTheDocument()
    expect(container.querySelector(".absolute.top-3.left-3")).not.toBeInTheDocument()
  })

  it("only shows the soon indicator when a countdown is supplied", () => {
    const { container } = render(<EventMedia {...baseProps} timeStatus={{ status: "soon" }} />)
    expect(screen.queryByText(/events:card.statuses.in/)).not.toBeInTheDocument()
    expect(screen.queryByText("common:statuses.live")).not.toBeInTheDocument()
    expect(container.querySelector(".absolute.top-3.right-3")).not.toBeInTheDocument()
  })

  it("reports both successful and failed image loads as ready", () => {
    const onReady = vi.fn()
    render(<EventMedia {...baseProps} onReady={onReady} />)
    const image = screen.getByRole("img", { name: "Event banner" })

    fireEvent.load(image)
    fireEvent.error(image)
    expect(onReady).toHaveBeenCalledTimes(2)
  })
})
