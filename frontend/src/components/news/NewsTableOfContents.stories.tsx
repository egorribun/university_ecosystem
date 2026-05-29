import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { NewsTableOfContents } from "./NewsTableOfContents"
import type { TocEntry } from "@/hooks/useArticleHeadings"

// Renders only when there are >= 3 headings (returns null otherwise).
const headings: TocEntry[] = [
  { id: "background", text: "Background", level: 2 },
  { id: "methodology", text: "Methodology", level: 2 },
  { id: "data-pipeline", text: "Data Pipeline", level: 3 },
  { id: "findings", text: "Key Findings", level: 2 },
  { id: "next-steps", text: "Next Steps", level: 3 },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 320 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsTableOfContents> = {
  title: "News/NewsTableOfContents",
  component: NewsTableOfContents,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof NewsTableOfContents>

export const Default: Story = { args: { headings }, decorators: [themed(false)] }

export const DarkMode: Story = {
  args: { headings },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
