import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { Spotlight } from "./Spotlight"

// Wave 196 SW2 — Spotlight Storybook fixture (LEAF tier batch 2).
//
// Hover-tracking radial spotlight wrapper. Renders its children with an
// `m.div` overlay (opacity-0 until group-hover, follows the cursor via a
// MotionValue) → LazyMotion decorator (preview.tsx has no global LazyMotion).
// The static snapshot shows the children; the spotlight reveals on mouse-move.
// No theme scope (global `--primary-main` / `--overlay-blur`). `render:` supplies
// the children (a sample card).
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const SampleCard = () => (
  <Spotlight className="rounded-2xl border border-glass-border bg-surface p-6 shadow-sm">
    <div style={{ width: 280 }}>
      <h3 className="text-base font-bold text-text-primary">Spotlight card</h3>
      <p className="mt-2 text-sm text-(--text-secondary)">
        Move the cursor over this card to reveal the brand-tinted radial spotlight.
      </p>
    </div>
  </Spotlight>
)

const meta: Meta<typeof Spotlight> = {
  title: "UI/Spotlight",
  component: Spotlight,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Spotlight>

export const Default: Story = {
  render: () => <SampleCard />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <SampleCard />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
