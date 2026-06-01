import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { Event } from "@/types/Event"
import { EventAboutEditor } from "./EventAboutEditor"

// Wave 199 SW1 — EventAboutEditor Storybook fixture (CONTEXT-tier, no infra).
//
// Renders inline (no portal). Save is a single fire-and-forget api.patch in
// try/catch wired to no-op callbacks, so a static story never hits the network.
// `editing` is internal useState (false on mount → read view); the Pencil edit
// affordance appears only when `canEdit`. `baseline` derives from event.about /
// event.about_en per `language`. Only useTranslation(["events","common"]) ambient.
//
// Variants: Default (canEdit, has about) / ReadOnly / Empty / DarkMode.

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
    "Практический воркшоп по конкурентным возможностям React 19: переходы, Suspense и новый компилятор.\nВо второй части — разбор паттернов из продакшена.",
  about_en:
    "A hands-on workshop on React 19 concurrent features: transitions, Suspense, and the new compiler.\nThe second half covers production-grade patterns.",
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

const meta: Meta<typeof EventAboutEditor> = {
  title: "Events/EventAboutEditor",
  component: EventAboutEditor,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    event: baseEvent,
    language: "ru",
    canEdit: true,
    onUpdate: asyncNoop,
    onError: noop,
    onSuccess: noop,
  },
}

export default meta
type Story = StoryObj<typeof EventAboutEditor>

export const Default: Story = { decorators: [themed(false)] }

export const ReadOnly: Story = {
  args: { canEdit: false },
  decorators: [themed(false)],
}

export const Empty: Story = {
  args: { event: { ...baseEvent, about: "", about_en: "" } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
