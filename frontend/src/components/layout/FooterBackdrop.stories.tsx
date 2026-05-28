import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { FooterBackdrop } from "./FooterBackdrop"

// Wave 193 SW4 — FooterBackdrop Storybook fixture.
//
// 2-prop family (isNarrow + prefersReducedMotion, no isMobile). SPECIAL
// CASE vs the other backdrops: the footer is theme-agnostic always-dark, so
// FooterBackdrop has NO `.X-theme` scope — its orb tokens (`--footer-orb-
// primary/secondary/sheen`) live in semantics.css `:root` (light, sky-300)
// + `.dark` (dark, sky-400) at :308 / :551. The `themed(dark)` factory
// therefore wraps in `bg-footer` (the blue-gradient / nav-dark surface
// utility, W175) instead of a theme class, with `.dark` as ANCESTOR for the
// dark orb values. Label uses `--text-on-footer` (constant white, W175 SW1)
// for contrast on the dark surface. Production sibling: Footer.tsx.
//
// Variants: Default (light footer = blue gradient) / DarkMode (dark footer =
// nav-dark gradient) / Narrow / ReducedMotion.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="bg-footer relative h-[600px] w-full overflow-hidden">
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-on-footer)">
          <span>Footer surface (always-dark) — orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof FooterBackdrop> = {
  title: "Layout/FooterBackdrop",
  component: FooterBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof FooterBackdrop>

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
