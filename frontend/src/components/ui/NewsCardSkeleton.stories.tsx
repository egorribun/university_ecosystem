import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import NewsCardSkeleton from "./NewsCardSkeleton"

// Wave 198 SW3 — NewsCardSkeleton Storybook fixture (shimmer; `featured?` prop).
//
// Loading placeholder for the news card (image + title + body lines + footer).
// `featured` switches to the wide lg:flex-row layout. Pure visual — Skeleton
// primitives + global card-matte/glass tokens. Scoped in `.news-theme`.
//
// Variants: Default / Featured / DarkMode.

const themed = (dark: boolean, width: number): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardSkeleton> = {
  title: "News/NewsCardSkeleton",
  component: NewsCardSkeleton,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { featured: false },
}

export default meta
type Story = StoryObj<typeof NewsCardSkeleton>

export const Default: Story = {
  decorators: [themed(false, 380)],
}

export const Featured: Story = {
  args: { featured: true },
  decorators: [themed(false, 720)],
}

export const DarkMode: Story = {
  decorators: [themed(true, 380)],
  parameters: { backgrounds: { default: "dark" } },
}
