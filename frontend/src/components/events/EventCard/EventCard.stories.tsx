import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { Event } from "@/types/Event"
import EventCard from "./EventCard"

// Wave 198 SW1 — EventCard Storybook fixture (CONTEXT-tier; ex-"A" card).
//
// EventCard is a logic-only layer: it takes Partial<Event> props, runs
// useEventCardLogic (NO network on mount — register/unregister are click-only and
// try/catch-guarded; useSpotlight/useNavigate/useAuth/i18n are ambient), and
// delegates rendering to EventCardView via its OWN <Suspense>. So no module mocking
// is needed — pure prop fixtures, same as the EventCardView story.
//
// Replaces the stale legacy story at components/EventCard.stories.tsx (old Event
// shape, no dark variant, "Components/EventCard" title). Co-located here next to
// the EventCardView/EventCardContent/EventCardHero stories; title "Events/EventCard".
//
// timeStatus ("soon"/"live"/"none") is COMPUTED from starts_at/ends_at, so the
// status variants use dates relative to NOW. The relative-time text drifts across
// Chromatic builds (collect-only auto-accepts; same class as the W194 heatmap).
//
// Variants: Default (soon) / Live / Past / WithoutImage / DarkMode.

const NOW = Date.now()
const H = 3_600_000
const D = 86_400_000
const SOON = {
  starts_at: new Date(NOW + 2 * H).toISOString(),
  ends_at: new Date(NOW + 4 * H).toISOString(),
}
const LIVE = {
  starts_at: new Date(NOW - 0.5 * H).toISOString(),
  ends_at: new Date(NOW + 1.5 * H).toISOString(),
}
const PAST = {
  starts_at: new Date(NOW - 2 * D).toISOString(),
  ends_at: new Date(NOW - 2 * D + 2 * H).toISOString(),
}

const BASE: Partial<Event> & { id: string } = {
  id: "evt-1",
  title: "Семинар по паттернам React 19",
  title_en: "React 19 Patterns Workshop",
  description: "Практическое погружение в конкурентные возможности React 19 и новый компилятор.",
  description_en: "A hands-on deep dive into React 19 concurrent features and the new compiler.",
  event_type: "workshop",
  event_type_en: "workshop",
  speaker: "Dr. Ivanova",
  location: "ГУК-305",
  location_en: "GUK-305",
  image_url: "https://picsum.photos/seed/eventcard/800/400",
  participant_count: 42,
  is_registered: false,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 380 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof EventCard> = {
  title: "Events/EventCard",
  component: EventCard,
  // W201: Date.now()-relative dates → component-computed timeStatus + relative-time
  // text drift day-over-day. Meta-level flag deep-merges into all variants. Skip snapshot.
  parameters: { layout: "centered", chromatic: { disableSnapshot: true } },
  tags: ["autodocs"],
  args: { ...BASE },
}

export default meta
type Story = StoryObj<typeof EventCard>

export const Default: Story = {
  args: { ...SOON },
  decorators: [themed(false)],
}

export const Live: Story = {
  args: { ...LIVE, is_registered: true },
  decorators: [themed(false)],
}

export const Past: Story = {
  args: { ...PAST },
  decorators: [themed(false)],
}

export const WithoutImage: Story = {
  args: { ...SOON, image_url: undefined },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...LIVE, is_registered: true },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
