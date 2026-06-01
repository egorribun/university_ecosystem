import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { EventQuickView } from "./EventQuickView"

// Wave 196 SW4 — EventQuickView Storybook fixture (CONTEXT-tier kickoff).
//
// Hover popover with an expanded event preview (category badge + date + title +
// description + stats). Renders from props alone when `visible` is true; uses
// framer-motion `m.*` + AnimatePresence → LazyMotion. `.events-theme` supplies the
// EventCategoryBadge tokens. The popover is `absolute` (pointer-events-none), so the
// decorator gives it a `relative` host; `position="bottom"` keeps it in view.
// `pauseAnimationAtEnd` freezes the entrance for Chromatic.
//
// Variants: Default (visible) / DarkMode.

const baseArgs = {
  visible: true,
  title: "React 19 Patterns Workshop",
  description: "A hands-on deep dive into React 19 concurrent features and the new compiler.",
  startsAt: "2026-06-15T14:00:00Z",
  location: "ГУК-305",
  participantCount: 42,
  category: "workshop" as const,
  position: "bottom" as const,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ position: "relative", width: 360, minHeight: 240 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof EventQuickView> = {
  title: "Events/EventQuickView",
  component: EventQuickView,
  parameters: {
    layout: "centered",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventQuickView>

export const Default: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
