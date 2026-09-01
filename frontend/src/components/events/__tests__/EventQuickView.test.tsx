import { render, screen } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", () => ({
  m: {
    div: ({
      children,
      initial,
      animate,
      exit,
      transition,
      ...props
    }: {
      children?: React.ReactNode
      initial?: unknown
      animate?: unknown
      exit?: unknown
      transition?: unknown
      [key: string]: unknown
    }) => (
      <div
        {...props}
        data-motion-initial={JSON.stringify(initial)}
        data-motion-animate={JSON.stringify(animate)}
        data-motion-exit={JSON.stringify(exit)}
        data-motion-transition={JSON.stringify(transition)}
      >
        {children}
      </div>
    ),
  },
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}))
const { reducedMotion } = vi.hoisted(() => ({ reducedMotion: vi.fn(() => false) }))
const { useTranslationMock, translationMock, formatDateMock } = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
    formatDateMock: vi.fn((value: string) => `date:${value}`),
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => reducedMotion() }))
vi.mock("react-i18next", () => ({ useTranslation: useTranslationMock }))
vi.mock("@/utils/date", () => ({ formatDate: formatDateMock }))

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
    expect(useTranslationMock).toHaveBeenCalledWith(["events"])
    expect(translationMock).toHaveBeenCalledWith("events:quickView.viewDetails")
    expect(formatDateMock).toHaveBeenCalledWith(
      baseProps.startsAt,
      expect.objectContaining({ day: "numeric", month: "short", hour12: false })
    )
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
    const { container } = render(
      <EventQuickView {...baseProps} position="bottom" category="conference" startsAt="" />
    )
    // bottom position still shows core content
    expect(screen.getByText("Quantum Computing Lecture")).toBeInTheDocument()
    expect(screen.getByText("events:categories.conference")).toBeInTheDocument()
    expect(container.querySelector("[data-motion-initial]")).toHaveAttribute(
      "data-motion-initial",
      JSON.stringify({ opacity: 0, y: -8, scale: 0.96 })
    )
    expect(container.querySelector("[data-motion-exit]")).toHaveAttribute(
      "data-motion-exit",
      JSON.stringify({ opacity: 0, y: -4, scale: 0.98 })
    )
    expect(container.querySelector("[data-motion-transition]")).toHaveAttribute(
      "data-motion-transition",
      JSON.stringify({ duration: 0.18, ease: [0.16, 1, 0.3, 1] })
    )
    expect(container.querySelector("svg.lucide-calendar")).not.toBeInTheDocument()
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
    const motion = document.querySelector("[data-motion-initial]")
    expect(motion).toHaveAttribute("data-motion-initial", "false")
    expect(motion).toHaveAttribute("data-motion-transition", JSON.stringify({ duration: 0 }))
  })

  it("omits the date row when startsAt is empty and keeps the title visible", () => {
    const { container } = render(<EventQuickView {...baseProps} startsAt="" />)
    expect(screen.getByText(baseProps.title)).toBeInTheDocument()
    expect(container.querySelector("svg.lucide-calendar")).not.toBeInTheDocument()
  })

  it("uses the default top position and preserves all stat labels", () => {
    const { container } = render(<EventQuickView {...baseProps} position={undefined} />)
    expect(container.querySelector("[data-motion-initial]")).toHaveAttribute(
      "data-motion-initial",
      JSON.stringify({ opacity: 0, y: 8, scale: 0.96 })
    )
    expect(screen.getByText("events:quickView.viewDetails")).toBeInTheDocument()
  })

  it("renders an empty date label when date formatting has no result", () => {
    formatDateMock.mockReturnValueOnce("")

    const { container } = render(<EventQuickView {...baseProps} />)

    const calendar = container.querySelector("svg.lucide-calendar")
    expect(calendar?.parentElement?.textContent).toBe("")
    expect(screen.queryByText(`date:${baseProps.startsAt}`)).not.toBeInTheDocument()
  })
})
