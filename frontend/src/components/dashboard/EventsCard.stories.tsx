import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { Event } from "@/types/Event"
import { dashboardEventsQueryKey } from "@/hooks/useDashboardEvents"
import { EventsCard } from "./EventsCard"

// Wave 199 SW1 — EventsCard story (CONTEXT-tier, no infra).
//
// Dashboard events card. useDashboardEvents() caches an EventsSnapshot
// ({ items: Event[] }) and `select`s to Event[], so the story seeds a per-story
// QueryClient at dashboardEventsQueryKey with `{ items }` (W198 NewChatModal
// seeding pattern). Uses framer-motion `m.*` + AnimatePresence → LazyMotion.
// Event fixtures include the REQUIRED readonly `image_url_optimized` field and
// future starts_at so the card sorts + renders the DateBullet list.
//
// Variants: Default (events) / Empty / DarkMode.

const NOW = Date.now()
const H = 3_600_000
const D = 86_400_000

const buildEvent = (n: number): Event => ({
  id: `evt-${n}`,
  title: `Мероприятие ${n}`,
  title_en: `Event ${n}`,
  location: "ГУК-305",
  starts_at: new Date(NOW + n * 6 * H).toISOString(),
  ends_at: new Date(NOW + n * 6 * H + 2 * H).toISOString(),
  created_by: "admin-1",
  created_at: new Date(NOW - D).toISOString(),
  is_active: true,
  image_url_optimized: null,
})

const EVENTS: Event[] = Array.from({ length: 4 }, (_, i) => buildEvent(i + 1))

const seeded = (events: Event[]): Decorator => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(dashboardEventsQueryKey, { items: events })
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <QueryClientProvider client={client}>
      <Story />
    </QueryClientProvider>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="dashboard-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 420 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof EventsCard> = {
  title: "Dashboard/EventsCard",
  component: EventsCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventsCard>

export const Default: Story = { decorators: [themed(false), seeded(EVENTS)] }

export const Empty: Story = { decorators: [themed(false), seeded([])] }

export const DarkMode: Story = {
  decorators: [themed(true), seeded(EVENTS)],
  parameters: { backgrounds: { default: "dark" } },
}
