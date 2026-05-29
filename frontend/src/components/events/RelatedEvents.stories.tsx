import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { Event } from "@/types/Event"
import { RelatedEvents } from "./RelatedEvents"

// Wave 197 SW2 — RelatedEvents Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// 3-column grid of same-type events. Takes an `items: Event[]` prop directly (no
// internal useQuery), so a story passes a fixture array. Each card is a TanStack
// <Link to="/events/$id"> (resolves in preview.tsx's root-only router) with
// SmartImage + an inferred EventCategoryBadge + a formatted date. Returns null
// when items is empty.
//
// Variants: Default (3 items, last image-less → gradient fallback) / DarkMode.

const baseEvent = {
  created_by: "u1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
}

const RELATED: Event[] = [
  {
    ...baseEvent,
    id: "e1",
    title: "Воркшоп по React 19",
    title_en: "React 19 Patterns Workshop",
    event_type: "workshop",
    event_type_en: "workshop",
    starts_at: "2026-06-15T14:00:00Z",
    ends_at: "2026-06-15T16:00:00Z",
    image_url: "https://picsum.photos/seed/related-e1/400/300",
  },
  {
    ...baseEvent,
    id: "e2",
    title: "Лекция: ИИ в образовании",
    title_en: "Lecture: AI in Education",
    event_type: "lecture",
    event_type_en: "lecture",
    starts_at: "2026-06-18T11:00:00Z",
    ends_at: "2026-06-18T12:30:00Z",
    image_url: "https://picsum.photos/seed/related-e2/400/300",
  },
  {
    ...baseEvent,
    id: "e3",
    title: "Карьерная ярмарка",
    title_en: "Career Fair",
    event_type: "fair",
    event_type_en: "fair",
    starts_at: "2026-06-20T10:00:00Z",
    ends_at: "2026-06-20T17:00:00Z",
    image_url: null,
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 880, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof RelatedEvents> = {
  title: "Events/RelatedEvents",
  component: RelatedEvents,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof RelatedEvents>

export const Default: Story = {
  args: { items: RELATED },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { items: RELATED },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
