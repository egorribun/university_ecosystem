import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ScaleIn } from "./ScaleIn"

// Wave 198 SW3 — ScaleIn Storybook fixture (ui/motion, m.div wrapper).
//
// Scale + fade entrance wrapper (variants hidden→visible on mount). Uses `m.div`,
// so the decorator supplies <LazyMotion features={domAnimation}>.
//
// Variants: Default / Pronounced (initialScale 0.8) / DarkMode.

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
      <strong>ScaleIn</strong>
      <p style={{ marginTop: 6, color: "var(--text-secondary)" }}>Scales up as it fades in.</p>
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

const meta: Meta<typeof ScaleIn> = {
  title: "Motion/ScaleIn",
  component: ScaleIn,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ScaleIn>

export const Default: Story = {
  render: () => (
    <ScaleIn>
      <DemoCard />
    </ScaleIn>
  ),
  decorators: [themed(false)],
}

export const Pronounced: Story = {
  render: () => (
    <ScaleIn initialScale={0.8}>
      <DemoCard />
    </ScaleIn>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <ScaleIn>
      <DemoCard />
    </ScaleIn>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
