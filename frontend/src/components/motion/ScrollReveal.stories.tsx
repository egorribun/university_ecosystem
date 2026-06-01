import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ScrollReveal } from "./ScrollReveal"

// Wave 198 SW2 — ScrollReveal Storybook fixture (motion/ family, named export).
//
// Reveals children when scrolled into view (IntersectionObserver → state-driven
// `m.div` variants). On mount in the Storybook viewport the element is already in
// view, so the observer fires immediately and children animate to "visible". Uses
// `m.*`, so the decorator supplies <LazyMotion features={domAnimation}>.
//
// Variants: Default (slide/up) / Pop / Scale / DarkMode.

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
      <strong>ScrollReveal</strong>
      <p style={{ marginTop: 6, color: "var(--text-secondary)" }}>
        Animates into view as it enters the viewport.
      </p>
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

const meta: Meta<typeof ScrollReveal> = {
  title: "Motion/ScrollReveal",
  component: ScrollReveal,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ScrollReveal>

export const Default: Story = {
  render: () => (
    <ScrollReveal mode="slide" direction="up">
      <DemoCard />
    </ScrollReveal>
  ),
  decorators: [themed(false)],
}

export const Pop: Story = {
  render: () => (
    <ScrollReveal mode="pop">
      <DemoCard />
    </ScrollReveal>
  ),
  decorators: [themed(false)],
}

export const Scale: Story = {
  render: () => (
    <ScrollReveal mode="scale">
      <DemoCard />
    </ScrollReveal>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <ScrollReveal mode="slide" direction="up">
      <DemoCard />
    </ScrollReveal>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
