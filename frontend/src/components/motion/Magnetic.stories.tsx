import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import Magnetic from "./Magnetic"

// Wave 198 SW2 — Magnetic Storybook fixture (motion/ family, pure wrapper).
//
// Plain <div> (no framer-motion since W124 SW1) that translates its children
// toward the cursor on mousemove via a CSS transform + cubic-bezier transition.
// Children render statically; hover over the story to feel the magnetic pull.
//
// Variants: Default (strength 0.5) / Strong (strength 0.8) / DarkMode.

function DemoButton() {
  return (
    <button
      type="button"
      style={{
        padding: "0.85rem 1.75rem",
        borderRadius: 9999,
        border: "none",
        fontWeight: 700,
        color: "var(--text-inverse)",
        background: "var(--color-brand)",
        cursor: "pointer",
        boxShadow: "0 10px 30px rgba(0,0,0,0.18)",
      }}
    >
      Hover me
    </button>
  )
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{
          background: "var(--bg-page)",
          padding: "4rem",
          minHeight: 220,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof Magnetic> = {
  title: "Motion/Magnetic",
  component: Magnetic,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Magnetic>

export const Default: Story = {
  render: () => (
    <Magnetic strength={0.5}>
      <DemoButton />
    </Magnetic>
  ),
  decorators: [themed(false)],
}

export const Strong: Story = {
  render: () => (
    <Magnetic strength={0.8}>
      <DemoButton />
    </Magnetic>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <Magnetic strength={0.5}>
      <DemoButton />
    </Magnetic>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
