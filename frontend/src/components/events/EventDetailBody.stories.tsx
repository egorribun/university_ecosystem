import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { Event } from "@/types/Event"
import { EventDetailBody } from "./EventDetailBody"

// Wave 199 SW1 — EventDetailBody Storybook fixture (CONTEXT-tier, no infra).
//
// Integration story: composes EventAboutEditor + EventFileManager into the
// detail-page body (About / divider / Files). No portal, no network on mount —
// the children's save/upload/delete are fire-and-forget try/catch wired to
// no-op callbacks. `isAdmin` toggles edit affordances in both sections.
//
// Variants: Admin (edit affordances) / Member (read-only) / DarkMode.

const NOW = Date.now()
const H = 3_600_000

const baseEvent: Event = {
  id: "evt-1",
  title: "Семинар по паттернам React 19",
  title_en: "React 19 Patterns Workshop",
  starts_at: new Date(NOW + 2 * H).toISOString(),
  ends_at: new Date(NOW + 4 * H).toISOString(),
  created_by: "admin-1",
  created_at: new Date(NOW - 86_400_000).toISOString(),
  is_active: true,
  image_url_optimized: null,
  about:
    "Практический воркшоп по конкурентным возможностям React 19: переходы, Suspense и новый компилятор.",
  about_en:
    "A hands-on workshop on React 19 concurrent features: transitions, Suspense, and the new compiler.",
  files: [
    {
      id: "f1",
      event_id: "evt-1",
      file_url: "/media/lecture-slides.pdf",
      description: "Lecture slides.pdf",
    },
    {
      id: "f2",
      event_id: "evt-1",
      file_url: "/media/reading-list.pdf",
      description: "Reading list.pdf",
    },
  ],
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 720 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const noop = () => {}
const asyncNoop = async () => {}

const meta: Meta<typeof EventDetailBody> = {
  title: "Events/EventDetailBody",
  component: EventDetailBody,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    event: baseEvent,
    language: "ru",
    isAdmin: true,
    onRefresh: asyncNoop,
    onError: noop,
    onSuccess: noop,
  },
}

export default meta
type Story = StoryObj<typeof EventDetailBody>

export const Admin: Story = { decorators: [themed(false)] }

export const Member: Story = {
  args: { isAdmin: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
