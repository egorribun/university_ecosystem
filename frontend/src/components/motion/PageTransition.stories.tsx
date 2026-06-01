import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import PageTransition from "./PageTransition"

// Wave 198 SW2 — PageTransition Storybook fixture (motion/ family, pure wrapper).
//
// Route-level entrance/exit transition. Lazy-loads framer-motion INTERNALLY (its
// own LazyMotion+domAnimation), so the story needs no LazyMotion decorator; under
// prefers-reduced-motion it renders children plainly. Children always render.
//
// Variants: Default / DarkMode.

function DemoPage() {
  return (
    <div style={{ maxWidth: 420 }}>
      <h2 style={{ margin: 0, fontWeight: 800, color: "var(--text-primary)" }}>Route content</h2>
      <p style={{ marginTop: 10, lineHeight: 1.6, color: "var(--text-secondary)" }}>
        Wrapped page content animates in with a spring on navigation and animates out on exit.
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

const meta: Meta<typeof PageTransition> = {
  title: "Motion/PageTransition",
  component: PageTransition,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof PageTransition>

export const Default: Story = {
  render: () => (
    <PageTransition>
      <DemoPage />
    </PageTransition>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <PageTransition>
      <DemoPage />
    </PageTransition>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
