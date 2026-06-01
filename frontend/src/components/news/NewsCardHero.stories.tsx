import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import NewsCardHero from "./NewsCardHero"

const IMG = "https://picsum.photos/seed/news-hero/720/400"
const CREATED = "2026-05-20T09:00:00Z"

/** Card-sized frame + `.news-theme` scope (news-badge-matte token). */
const framed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="group relative overflow-hidden rounded-2xl"
          style={{ width: 360, height: 200 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardHero> = {
  title: "News/NewsCardHero",
  component: NewsCardHero,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof NewsCardHero>

export const Default: Story = {
  args: {
    image_url: IMG,
    title: "University Announces New AI Research Center",
    created_at: CREATED,
  },
  decorators: [framed(false)],
}

export const NoImage: Story = {
  args: { title: "Campus Library Extends Hours for Finals Week", created_at: CREATED },
  decorators: [framed(false)],
  parameters: {
    docs: { description: { story: "Fallback article icon when no image is supplied." } },
  },
}

export const DarkMode: Story = {
  args: { ...Default.args },
  decorators: [framed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
