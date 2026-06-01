import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { NewsDetailNavigation } from "./NewsDetailNavigation"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 768, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsDetailNavigation> = {
  title: "News/NewsDetailNavigation",
  component: NewsDetailNavigation,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof NewsDetailNavigation>

export const Both: Story = {
  args: {
    prevId: "n-1",
    nextId: "n-3",
    prevTitle: "Campus Library Extends Hours for Finals Week",
    nextTitle: "Student Council Election Results Announced",
  },
  decorators: [themed(false)],
}

export const OnlyNext: Story = {
  args: {
    prevId: null,
    nextId: "n-3",
    prevTitle: null,
    nextTitle: "Student Council Election Results Announced",
  },
  decorators: [themed(false)],
}

export const OnlyPrev: Story = {
  args: {
    prevId: "n-1",
    nextId: null,
    prevTitle: "Campus Library Extends Hours for Finals Week",
    nextTitle: null,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...Both.args },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
