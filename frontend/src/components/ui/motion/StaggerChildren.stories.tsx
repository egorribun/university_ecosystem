import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { CSSProperties } from "react"
import { StaggerChildren } from "./StaggerChildren"

// Wave 198 SW3 — StaggerChildren Storybook fixture (ui/motion, CSS stagger).
//
// Plain <div> + IntersectionObserver that sets data-visible="true" on `.stagger-item`
// children when in view (or immediately under prefers-reduced-motion). On mount in
// the Storybook viewport the IO fires, revealing the items with a cascading delay
// driven by their `--stagger-i` index. No framer runtime → no LazyMotion needed.
//
// Variants: Default / DarkMode.

function StaggerItem({ index, label }: { index: number; label: string }) {
  return (
    <div className="stagger-item" style={{ "--stagger-i": index } as CSSProperties}>
      <div
        style={{
          padding: "1.25rem 1.5rem",
          borderRadius: 14,
          background: "var(--bg-surface)",
          color: "var(--text-primary)",
          border: "1px solid var(--glass-border)",
        }}
      >
        <strong>{label}</strong>
      </div>
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

const meta: Meta<typeof StaggerChildren> = {
  title: "Motion/StaggerChildren",
  component: StaggerChildren,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof StaggerChildren>

const Items = () => (
  <div style={{ width: 300 }}>
    <StaggerChildren className="flex flex-col gap-3">
      <StaggerItem index={0} label="First item" />
      <StaggerItem index={1} label="Second item" />
      <StaggerItem index={2} label="Third item" />
    </StaggerChildren>
  </div>
)

export const Default: Story = {
  render: () => <Items />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <Items />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
