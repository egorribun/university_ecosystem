import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { NewsDetailHero } from "./NewsDetailHero"

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

const meta: Meta<typeof NewsDetailHero> = {
  title: "News/NewsDetailHero",
  component: NewsDetailHero,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof NewsDetailHero>

export const Default: Story = {
  args: {
    imageUrl: "https://picsum.photos/seed/news-detail/1200/675",
    displayTitle: "University Announces New AI Research Center",
  },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Hero figure with aspect-aware framing + zoom-to-lightbox." } },
  },
}

export const DarkMode: Story = {
  args: { ...Default.args },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
