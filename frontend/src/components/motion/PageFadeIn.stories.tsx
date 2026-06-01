import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import PageFadeIn from "./PageFadeIn"

// Wave 198 SW2 — PageFadeIn Storybook fixture (motion/ family, pure wrapper).
//
// `<div data-page-fade data-ready>` page-level entrance wrapper. Sets data-ready
// on the first rAF (visible thereafter); honours prefers-reduced-motion. No framer
// runtime — pure div + CSS. Children always render.
//
// Variants: Default / SoftBlur (effect="soft-blur") / DarkMode.

function DemoPage() {
  return (
    <div style={{ maxWidth: 420 }}>
      <h2 style={{ margin: 0, fontWeight: 800, color: "var(--text-primary)" }}>Page heading</h2>
      <p style={{ marginTop: 10, lineHeight: 1.6, color: "var(--text-secondary)" }}>
        The whole page content fades in once on mount with a configurable delay and an optional
        soft-blur effect.
      </p>
    </div>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2.5rem", minHeight: 220 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof PageFadeIn> = {
  title: "Motion/PageFadeIn",
  component: PageFadeIn,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof PageFadeIn>

export const Default: Story = {
  render: () => (
    <PageFadeIn delay={80}>
      <DemoPage />
    </PageFadeIn>
  ),
  decorators: [themed(false)],
}

export const SoftBlur: Story = {
  render: () => (
    <PageFadeIn delay={80} effect="soft-blur">
      <DemoPage />
    </PageFadeIn>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <PageFadeIn delay={80}>
      <DemoPage />
    </PageFadeIn>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
