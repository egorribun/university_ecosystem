import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { FadeIn } from "./FadeIn"

// Wave 198 SW3 — FadeIn Storybook fixture (ui/motion, m.div wrapper).
//
// Directional fade-in entrance wrapper (variants hidden→visible on mount). Uses
// `m.div`, so the decorator supplies <LazyMotion features={domAnimation}>.
//
// Variants: Default (up) / FromLeft / DarkMode.

function DemoCard() {
  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        borderRadius: 16,
        maxWidth: 360,
        background: "var(--bg-surface)",
        color: "var(--text-primary)",
        border: "1px solid var(--glass-border)",
      }}
    >
      <strong>FadeIn</strong>
      <p style={{ marginTop: 6, color: "var(--text-secondary)" }}>Fades + slides into place.</p>
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", padding: "2.5rem", minHeight: 200 }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof FadeIn> = {
  title: "Motion/FadeIn",
  component: FadeIn,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof FadeIn>

export const Default: Story = {
  render: () => (
    <FadeIn>
      <DemoCard />
    </FadeIn>
  ),
  decorators: [themed(false)],
}

export const FromLeft: Story = {
  render: () => (
    <FadeIn direction="left" distance={40}>
      <DemoCard />
    </FadeIn>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <FadeIn>
      <DemoCard />
    </FadeIn>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
