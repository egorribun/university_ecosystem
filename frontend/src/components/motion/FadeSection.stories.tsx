import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import FadeSection from "./FadeSection"

// Wave 198 SW2 — FadeSection Storybook fixture (motion/ family, pure wrapper).
//
// Thin `<div data-fade style={{ --fade-delay }}>` wrapper around children — no
// framer-motion, no opacity gate (the data-fade hook has no opacity:0 CSS rule),
// so children render visibly. Forwards all native div attributes.
//
// Variants: Default / DarkMode.

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
      <strong>FadeSection</strong>
      <p style={{ marginTop: 6, color: "var(--text-secondary)" }}>
        Children wrapped with a staggered entrance delay.
      </p>
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2.5rem", minHeight: 200 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof FadeSection> = {
  title: "Motion/FadeSection",
  component: FadeSection,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof FadeSection>

export const Default: Story = {
  render: () => (
    <FadeSection delay="120ms">
      <DemoCard />
    </FadeSection>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <FadeSection delay="120ms">
      <DemoCard />
    </FadeSection>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
