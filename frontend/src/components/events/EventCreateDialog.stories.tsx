import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { EventCreateDialog } from "./EventCreateDialog"

// Wave 199 SW1 — EventCreateDialog Storybook fixture (CONTEXT-tier, no infra).
//
// The Dialog from @/components/settings renders via ReactDOM.createPortal to
// document.body, so the dialog content escapes any `.dark`/`.events-theme`
// decorator wrapper → **default-theme-only** (EventQrDialog pattern), no
// DarkMode variant. It animates with framer-motion `m.div` → LazyMotion is
// required. Form state is local useState; uploadEventImage is click-only
// (try/finally), so a static `open` story never hits the network on mount.
// Tokens used are :root-level (--text-primary/-secondary/--bg-surface/etc.),
// so the default theme renders correctly outside the theme scope.
//
// Variants: Russian (language="ru") / English (language="en").

const withMotion: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <Story />
  </LazyMotion>
)

const meta: Meta<typeof EventCreateDialog> = {
  title: "Events/EventCreateDialog",
  component: EventCreateDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withMotion],
  args: {
    open: true,
    onClose: () => {},
    onCreated: () => {},
    language: "ru",
  },
}

export default meta
type Story = StoryObj<typeof EventCreateDialog>

export const Russian: Story = {}

export const English: Story = {
  args: { language: "en" },
}
