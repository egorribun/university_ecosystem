import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventMedia } from "@/components/events/EventCard/EventMedia"

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
  it("renders the image button and the event type badge", () => {
    render(<EventMedia {...baseProps} />)
    expect(screen.getByText("Workshop")).toBeInTheDocument()
    expect(screen.getByRole("button")).toBeEnabled()
  })

  it("shows the live status indicator", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "live" }} />)
    expect(screen.getByText("common:statuses.live")).toBeInTheDocument()
  })

  it("shows the soon status indicator with the countdown text", () => {
    render(<EventMedia {...baseProps} timeStatus={{ status: "soon", timeText: "15m" }} />)
    expect(screen.getByText(/events:card.statuses.in/)).toBeInTheDocument()
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
})
