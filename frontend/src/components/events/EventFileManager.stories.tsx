import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { Event } from "@/types/Event"
import { EventFileManager } from "./EventFileManager"

// Wave 199 SW1 — EventFileManager Storybook fixture (CONTEXT-tier, no infra).
//
// Renders inline (no portal). Upload/delete are fire-and-forget try/catch
// (api.post/api.delete) wired to no-op callbacks; useActionState + useOptimistic
// drive the form locally, so a static story never hits the network on mount.
// Only useTranslation(["events","common"]) is ambient (preview.tsx I18nextProvider).
// `event.files` (EventFileOut[]) seeds the list; `canEdit` toggles the upload form.
// Full `Event` fixture includes the REQUIRED readonly `image_url_optimized` field.
//
// Variants: Default (canEdit + files) / ReadOnly / Empty / DarkMode.

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
          <div style={{ width: 560 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const noop = () => {}
const asyncNoop = async () => {}

const meta: Meta<typeof EventFileManager> = {
  title: "Events/EventFileManager",
  component: EventFileManager,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    event: baseEvent,
    canEdit: true,
    onUpdate: asyncNoop,
    onError: noop,
    onSuccess: noop,
  },
}

export default meta
type Story = StoryObj<typeof EventFileManager>

export const Default: Story = { decorators: [themed(false)] }

export const ReadOnly: Story = {
  args: { canEdit: false },
  decorators: [themed(false)],
}

export const Empty: Story = {
  args: { event: { ...baseEvent, files: [] } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
