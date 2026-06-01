import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { NewsBackdrop } from "./NewsBackdrop"

// Wave 193 SW4 — NewsBackdrop Storybook fixture.
//
// 2-prop family (isNarrow REQUIRED + prefersReducedMotion optional, no
// isMobile). Sky ambient orbs scoped under `.news-theme` (tokens/news.css),
// so the `themed(dark)` factory wraps in `.news-theme` with `.dark` as an
// ANCESTOR for the dark variant. Production wrapper: NewsFeature.tsx:102.
// isNarrow is REQUIRED (no default) — passed explicitly in every variant.
//
// Variants: Default / DarkMode / Narrow / ReducedMotion.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="news-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>News surface — sky orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsBackdrop> = {
  title: "News/NewsBackdrop",
  component: NewsBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsBackdrop>

export const Default: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: false,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: false,
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [themed(true)],
}

export const Narrow: Story = {
  args: {
    isNarrow: true,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
  decorators: [themed(false)],
}

export const ReducedMotion: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: true,
  },
  decorators: [themed(false)],
}
