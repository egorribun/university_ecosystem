import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AuthBackdrop } from "../auth/AuthBackdrop"
import { DashboardBackdrop } from "../dashboard/DashboardBackdrop"
import { EventsBackdrop } from "../events/EventsBackdrop"
import { FooterBackdrop } from "../layout/FooterBackdrop"
import { NewsBackdrop } from "../news/NewsBackdrop"
import { ProfileBackdrop } from "../profile/ProfileBackdrop"
import { SettingsBackdrop } from "../settings/SettingsBackdrop"
import { ActivityBackdrop } from "../../features/activity/components/ActivityBackdrop"

describe("Presentational Backdrops Coverage Sweep", () => {
  it("renders AuthBackdrop under all branches", () => {
    const { rerender, container } = render(<AuthBackdrop />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<AuthBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<AuthBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<AuthBackdrop isNarrow={true} isMobile={false} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders DashboardBackdrop under all branches", () => {
    const { rerender, container } = render(
      <DashboardBackdrop isNarrow={false} prefersReducedMotion={false} />
    )
    expect(container.firstChild).toBeInTheDocument()

    rerender(<DashboardBackdrop isNarrow={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<DashboardBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders EventsBackdrop under all branches", () => {
    const { rerender, container } = render(<EventsBackdrop />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<EventsBackdrop isNarrow={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<EventsBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<EventsBackdrop isNarrow={true} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders FooterBackdrop under all branches", () => {
    const { rerender, container } = render(<FooterBackdrop />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<FooterBackdrop isNarrow={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<FooterBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<FooterBackdrop isNarrow={true} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders NewsBackdrop under all branches", () => {
    const { rerender, container } = render(<NewsBackdrop isNarrow={false} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<NewsBackdrop isNarrow={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<NewsBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<NewsBackdrop isNarrow={true} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders ProfileBackdrop under all branches", () => {
    const { rerender, container } = render(<ProfileBackdrop />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<ProfileBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<ProfileBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders SettingsBackdrop under all branches", () => {
    const { rerender, container } = render(<SettingsBackdrop />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<SettingsBackdrop isNarrow={true} isMobile={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<SettingsBackdrop isNarrow={false} isMobile={false} prefersReducedMotion={false} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it("renders ActivityBackdrop under all branches", () => {
    const { rerender, container } = render(
      <ActivityBackdrop isNarrow={false} prefersReducedMotion={false} />
    )
    expect(container.firstChild).toBeInTheDocument()

    rerender(<ActivityBackdrop isNarrow={true} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()

    rerender(<ActivityBackdrop isNarrow={false} prefersReducedMotion={true} />)
    expect(container.firstChild).toBeInTheDocument()
  })
})
