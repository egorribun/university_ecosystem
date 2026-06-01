import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import CardShell from "./CardShell"

// Wave 196 SW3 — CardShell Storybook fixture (LEAF tier batch 2).
//
// Tone-accented matte card wrapper for the Activity dashboard. Renders from
// `tone` + `children` + `aria-label`; the tone maps to an `--_accent` CSS var
// (`.activity-card-matte`). `.activity-theme` supplies the `--activity-*-accent`
// tokens. No framer-motion. `render:` provides sample children.
//
// Variants: Neutral / Success / Info / Warning / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme"
        style={{ background: "var(--bg-page)", padding: "2rem", width: 320 }}
      >
        <Story />
      </div>
    </div>
  )
}

const Sample = ({ label }: { label: string }) => (
  <>
    <p className="text-micro font-semibold uppercase tracking-wider text-text-tertiary">{label}</p>
    <p className="text-3xl font-black tracking-tighter text-text-primary">92%</p>
    <p className="text-sm text-text-secondary">Across the last 30 days</p>
  </>
)

const meta: Meta<typeof CardShell> = {
  title: "Features/Activity/CardShell",
  component: CardShell,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof CardShell>

export const Neutral: Story = {
  render: () => (
    <CardShell tone="neutral" aria-label="Neutral card">
      <Sample label="Neutral" />
    </CardShell>
  ),
  decorators: [themed(false)],
}

export const Success: Story = {
  render: () => (
    <CardShell tone="success" aria-label="Attendance card">
      <Sample label="Attendance" />
    </CardShell>
  ),
  decorators: [themed(false)],
}

export const Info: Story = {
  render: () => (
    <CardShell tone="info" aria-label="Grades card">
      <Sample label="Grades" />
    </CardShell>
  ),
  decorators: [themed(false)],
}

export const Warning: Story = {
  render: () => (
    <CardShell tone="warning" aria-label="Participation card">
      <Sample label="Participation" />
    </CardShell>
  ),
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => (
    <CardShell tone="success" aria-label="Attendance card">
      <Sample label="Attendance" />
    </CardShell>
  ),
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
