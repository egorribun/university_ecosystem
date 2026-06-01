import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { DetailRow } from "./DetailRow"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 480, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof DetailRow> = {
  title: "Profile/DetailRow",
  component: DetailRow,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof DetailRow>

export const Default: Story = {
  args: { label: "Institute", value: "Institute of Information Systems" },
  decorators: [themed(false)],
}

export const LongValue: Story = {
  args: {
    label: "About",
    value:
      "Third-year student focused on distributed systems and machine learning, with a side interest in design systems and accessibility.",
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { label: "Track", value: "Applied Informatics" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
