import { screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import { RelatedEvents } from "@/components/events/RelatedEvents"
import type { Event } from "@/types/Event"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const ITEMS: Event[] = [
  {
    id: "e1",
    title: "Воркшоп по React 19",
    title_en: "React 19 Patterns Workshop",
    event_type: "workshop",
    starts_at: "2026-06-15T14:00:00Z",
    ends_at: "2026-06-15T16:00:00Z",
    created_by: "u1",
    created_at: "2026-05-01T10:00:00Z",
    is_active: true,
    image_url: "https://picsum.photos/seed/related-e1/400/300",
    image_url_optimized: null,
  },
  {
    id: "e2",
    title: "Лекция: ИИ в образовании",
    title_en: "Lecture: AI in Education",
    event_type: "lecture",
    starts_at: "2026-06-18T11:00:00Z",
    ends_at: "2026-06-18T12:30:00Z",
    created_by: "u1",
    created_at: "2026-05-01T10:00:00Z",
    is_active: true,
    image_url: null,
    image_url_optimized: null,
  },
]

const extraRoutes = [{ path: "/events/$id", Component: () => <div>Event detail</div> }]

describe("RelatedEvents", () => {
  it("renders one linked card per event", async () => {
    await renderWithRouter({ ui: () => <RelatedEvents items={ITEMS} />, extraRoutes })
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(ITEMS.length)
    expect(links[0]!.getAttribute("href")).toContain("/events/e1")
    expect(links[1]!.getAttribute("href")).toContain("/events/e2")
  })

  it("renders nothing when there are no related events", async () => {
    await renderWithRouter({ ui: () => <RelatedEvents items={[]} />, extraRoutes })
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })
})
