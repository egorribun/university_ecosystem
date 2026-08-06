import { render, screen } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
const { reducedMotion } = vi.hoisted(() => ({ reducedMotion: vi.fn(() => false) }))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => reducedMotion() }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventQuickView } from "@/components/events/EventQuickView"

const baseProps = {
  visible: true,
  title: "Quantum Computing Lecture",
  description: "An introductory survey of qubits and gates.",
  startsAt: "2026-01-15T10:00:00.000Z",
  endsAt: "2026-01-15T12:00:00.000Z",
  location: "Auditorium 42",
  participantCount: 137,
  category: "lecture" as const,
}

describe("EventQuickView", () => {
  afterEach(() => {
    reducedMotion.mockReturnValue(false)
  })

  it("renders title, description, location, participant count and the view-details CTA", () => {
    render(<EventQuickView {...baseProps} />)
    expect(screen.getByText("Quantum Computing Lecture")).toBeInTheDocument()
    expect(screen.getByText("An introductory survey of qubits and gates.")).toBeInTheDocument()
    expect(screen.getByText("Auditorium 42")).toBeInTheDocument()
    expect(screen.getByText("137")).toBeInTheDocument()
    expect(screen.getByText("events:quickView.viewDetails")).toBeInTheDocument()
    // category branch — badge renders the localized label key
    expect(screen.getByText("events:categories.lecture")).toBeInTheDocument()
  })

  it("renders nothing when visible=false", () => {
    const { container } = render(<EventQuickView {...baseProps} visible={false} />)
    expect(screen.queryByText("Quantum Computing Lecture")).not.toBeInTheDocument()
    expect(container.querySelector("h4")).toBeNull()
  })

  it("omits the description and location blocks when those props are empty", () => {
    render(
      <EventQuickView {...baseProps} description="" location={undefined} participantCount={0} />
    )
    expect(
      screen.queryByText("An introductory survey of qubits and gates.")
    ).not.toBeInTheDocument()
    expect(screen.queryByText("Auditorium 42")).not.toBeInTheDocument()
    // participant count still rendered (0) + title present
    expect(screen.getByText("Quantum Computing Lecture")).toBeInTheDocument()
    expect(screen.getByText("0")).toBeInTheDocument()
  })

  it("renders the bottom-position variant and a different category branch", () => {
    render(<EventQuickView {...baseProps} position="bottom" category="conference" startsAt="" />)
    // bottom position still shows core content
    expect(screen.getByText("Quantum Computing Lecture")).toBeInTheDocument()
    expect(screen.getByText("events:categories.conference")).toBeInTheDocument()
  })

  it("uses reduced-motion transitions and tolerates an invalid date", () => {
    reducedMotion.mockReturnValue(true)
    render(
      <EventQuickView
        {...baseProps}
        position="bottom"
        startsAt="not-a-date"
        description=""
        location={undefined}
      />
    )

    expect(screen.getByText("Quantum Computing Lecture")).toBeInTheDocument()
    expect(
      screen.queryByText("An introductory survey of qubits and gates.")
    ).not.toBeInTheDocument()
  })
})
