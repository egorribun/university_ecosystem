import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import NotificationsBell from "./NotificationsBell"

// Wave 198 SW4 — NotificationsBell Storybook fixture (navbar action).
//
// Zero-prop bell button. Drives state from useNotifications() (ambient QueryClient);
// with no backend the list query fails silently (retry:false) → empty bell. The
// generated client returns errors instead of throwing, so the on-mount
// checkSchedule() fire-and-forget resolves (no unhandled rejection). The dropdown
// (m.div + createPortal) only mounts on click; LazyMotion supplied for safety.
//
// Variants: Default (closed, empty) / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", padding: "2.5rem", minHeight: 120 }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NotificationsBell> = {
  title: "Feedback/NotificationsBell",
  component: NotificationsBell,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NotificationsBell>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
