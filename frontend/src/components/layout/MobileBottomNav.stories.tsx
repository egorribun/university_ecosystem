import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import MobileBottomNav from "./MobileBottomNav"

// Wave 199 SW1 — MobileBottomNav story (CONTEXT-tier, no infra).
//
// Zero-prop fixed bottom tab bar. Reads pathname from the ambient
// RouterProvider (preview.tsx, "/"), so the dashboard tab is active. It is
// `md:hidden` (only visible below 768px), so the mobile viewport param makes it
// visible; at desktop width it stays in the DOM but display:none. Uses
// framer-motion `m.*` + AnimatePresence + useSlidingIndicator (ResizeObserver)
// → LazyMotion required. hideOn excludes auth routes (not matched at "/").
//
// Variants: Default (mobile viewport) / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", minHeight: 480 }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MobileBottomNav> = {
  title: "Layout/MobileBottomNav",
  component: MobileBottomNav,
  parameters: {
    layout: "fullscreen",
    viewport: { defaultViewport: "mobile1" },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MobileBottomNav>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
