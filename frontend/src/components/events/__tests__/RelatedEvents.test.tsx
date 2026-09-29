import { screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import {
  RELATED_EVENT_CARD_TRANSLATION_NAMESPACES,
  RELATED_EVENTS_TRANSLATION_NAMESPACES,
  RelatedEvents,
} from "@/components/events/RelatedEvents"
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
  it("keeps the translation namespace contracts explicit", () => {
    expect(RELATED_EVENTS_TRANSLATION_NAMESPACES).toStrictEqual(["events", "common"])
    expect(RELATED_EVENT_CARD_TRANSLATION_NAMESPACES).toStrictEqual(["events"])
  })

  it("renders one linked card per event", async () => {
    await renderWithRouter({ ui: () => <RelatedEvents items={ITEMS} />, extraRoutes })
    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(ITEMS.length)
    expect(links[0]!.getAttribute("href")).toContain("/events/e1")
    expect(links[1]!.getAttribute("href")).toContain("/events/e2")

    const section = screen.getByRole("region", { name: "Related events" })
    expect(section).toHaveClass("mt-10")
    expect(screen.getByRole("heading", { level: 2 })).toHaveClass(
      "text-lg",
      "font-bold",
      "text-text-primary",
      "mb-4"
    )
    expect(screen.getByRole("heading", { level: 2 })).toHaveAttribute(
      "style",
      expect.stringContaining("scroll-margin-top: 5rem")
    )
    expect(screen.getByRole("heading", { level: 3, name: ITEMS[0]!.title_en! })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 3, name: ITEMS[1]!.title_en! })).toBeInTheDocument()
    expect(screen.getAllByText("View details")).toHaveLength(ITEMS.length)
    expect(screen.getByAltText(ITEMS[0]!.title_en!)).toHaveAttribute("src", ITEMS[0]!.image_url)
    expect(screen.getByText("Jun 15")).toBeInTheDocument()
    expect(screen.getByText("Jun 18")).toBeInTheDocument()
    expect(section.querySelector(".grid")).toHaveClass("grid-cols-1", "sm:grid-cols-3", "gap-4")
  })

  it("renders nothing when there are no related events", async () => {
    await renderWithRouter({ ui: () => <RelatedEvents items={[]} />, extraRoutes })
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Related events" })).not.toBeInTheDocument()
  })

  it("uses safe fallbacks for optional title, category, date, and image fields", async () => {
    const sparseEvent = {
      ...ITEMS[0],
      id: "sparse",
      // The API is untrusted at this boundary. A non-string title must use
      // the same empty fallback as an absent title instead of leaking a
      // number into the card heading.
      title: 123,
      title_en: undefined,
      event_type: undefined,
      event_type_en: undefined,
      starts_at: undefined,
      image_url: null,
    } as unknown as Event

    await renderWithRouter({ ui: () => <RelatedEvents items={[sparseEvent]} />, extraRoutes })
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "/events/sparse")
    expect(link).toHaveClass(
      "group",
      "relative",
      "rounded-xl",
      "card-matte",
      "glass-noise",
      "border",
      "overflow-hidden",
      "transition-all",
      "duration-slower",
      "hover:-translate-y-1"
    )
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(link.querySelector("svg")).toHaveClass("h-8", "w-8", "text-brand/(--opacity-medium)")
    expect(screen.getByRole("heading", { level: 3 })).toBeEmptyDOMElement()
    expect(
      [...link.querySelectorAll("span")].filter((span) => span.className.includes("text-[11px]"))
    ).toHaveLength(1)
    expect(screen.queryByText("View details")).toBeInTheDocument()
  })

  it("uses the English title and image alt text when the active language is English", async () => {
    await renderWithRouter({ ui: () => <RelatedEvents items={[ITEMS[0]!]} />, extraRoutes })

    const link = screen.getByRole("link")
    const title = screen.getByRole("heading", { level: 3 })
    expect(title).toHaveTextContent(ITEMS[0]!.title_en!)
    expect(screen.getByAltText(ITEMS[0]!.title_en!)).toBeInTheDocument()
    expect(link.querySelector(".absolute.top-2.left-2")).toBeInTheDocument()
  })

  it("keeps a present date visible and uses the fallback category when type is unknown", async () => {
    const unknownType = { ...ITEMS[0]!, event_type: "miscellaneous" }
    await renderWithRouter({ ui: () => <RelatedEvents items={[unknownType]} />, extraRoutes })

    const link = screen.getByRole("link")
    expect(screen.getByText("Jun 15")).toBeInTheDocument()
    expect(screen.getByText("Other")).toBeInTheDocument()
    expect(
      [...link.querySelectorAll("span")].filter((span) => span.textContent === "Jun 15")
    ).toHaveLength(1)
  })

  it("uses the English event type only when the primary type is nullish", async () => {
    const missingPrimary = {
      ...ITEMS[0]!,
      id: "missing-primary-type",
      event_type: undefined,
      event_type_en: "conference",
    } as unknown as Event
    await renderWithRouter({ ui: () => <RelatedEvents items={[missingPrimary]} />, extraRoutes })
    expect(screen.getByText("Conference")).toBeInTheDocument()

    const emptyPrimary = {
      ...ITEMS[0]!,
      id: "empty-primary-type",
      event_type: "",
      event_type_en: "conference",
    }
    await renderWithRouter({ ui: () => <RelatedEvents items={[emptyPrimary]} />, extraRoutes })
    expect(screen.getByText("Other")).toBeInTheDocument()

    const nullPrimary = {
      ...ITEMS[0]!,
      id: "null-primary-type",
      event_type: null,
      event_type_en: "conference",
    }
    await renderWithRouter({ ui: () => <RelatedEvents items={[nullPrimary]} />, extraRoutes })
    expect(screen.getAllByText("Conference")).toHaveLength(2)
  })

  it("keeps the primary title for the Russian locale", async () => {
    const previousLanguage = window.localStorage.getItem("ue:language")
    window.localStorage.setItem("ue:language", "ru")

    try {
      await renderWithRouter({ ui: () => <RelatedEvents items={[ITEMS[0]!]} />, extraRoutes })
      expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(ITEMS[0]!.title)
    } finally {
      if (previousLanguage === null) window.localStorage.removeItem("ue:language")
      else window.localStorage.setItem("ue:language", previousLanguage)
    }
  })
})
