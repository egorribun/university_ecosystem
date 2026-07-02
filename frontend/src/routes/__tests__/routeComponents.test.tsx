/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { Route as EventsDetailRoute } from "../_auth/events.$id"
import { Route as ScheduleRoute } from "../_auth/schedule"
import { Route as SettingsRoute } from "../_auth/settings"

// Mock the lazy loaded pages
vi.mock("@/pages/EventDetail", () => ({
  default: () => <div data-testid="lazy-event-detail" />,
}))

vi.mock("@/pages/Schedule", () => ({
  default: () => <div data-testid="lazy-schedule" />,
}))

vi.mock("@/pages/Settings", () => ({
  default: () => <div data-testid="lazy-settings" />,
}))

describe("Route Components", () => {
  it("renders EventsDetailRoute successfully using lazy import", async () => {
    const Component = EventsDetailRoute.options.component as any
    expect(Component).toBeDefined()

    render(<Component />)

    // Wait for the lazy component to be rendered
    await waitFor(() => {
      expect(screen.getByTestId("lazy-event-detail")).toBeInTheDocument()
    })
  })

  it("renders ScheduleRoute successfully using lazy import", async () => {
    const Component = ScheduleRoute.options.component as any
    expect(Component).toBeDefined()

    render(<Component />)

    await waitFor(() => {
      expect(screen.getByTestId("lazy-schedule")).toBeInTheDocument()
    })
  })

  it("renders SettingsRoute successfully using lazy import", async () => {
    const Component = SettingsRoute.options.component as any
    expect(Component).toBeDefined()

    render(<Component />)

    await waitFor(() => {
      expect(screen.getByTestId("lazy-settings")).toBeInTheDocument()
    })
  })
})
