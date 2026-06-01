import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { ActivityBackdrop } from "./ActivityBackdrop"

// Wave 193 SW2 — ActivityBackdrop Storybook fixture.
//
// First story co-located under `src/features/` — only discoverable since
// the W193 SW1 glob widen (`../src/features/**`). Proves the widen
// end-to-end.
//
// Pattern source: `frontend/src/components/messenger/MessengerBackdrop.stories.tsx`
// (W192 SW2 / W176 SW5 template), with one deliberate deviation forced by
// Phase 3 verification: ActivityBackdrop's orb tokens (`--activity-hero-orb`,
// `--activity-hero-highlight`, `--grad-activity-conic`, `--activity-orb-3`)
// are SCOPE-defined under `.activity-theme` (tokens/activity.css:34 light +
// :123 dark) — NOT `@property`-registered globals like the messenger orbs.
// So the decorator MUST wrap the backdrop in `.activity-theme`, and the
// dark variant needs `.dark` as an ANCESTOR of `.activity-theme` (the
// `.dark .activity-theme` descendant selector). Storybook nests story
// decorators INSIDE meta decorators, so the messenger "meta=theme,
// story=.dark" split would produce the wrong order — hence the single
// `themed(dark)` factory that controls the full `.dark > .activity-theme`
// subtree per variant. Production wrapper: ActivityFeature.tsx:74.
//
// Variants: Default / DarkMode / Narrow (drops desktop-only highlight +
// conic) / ReducedMotion (drops the drifting conic animation). Props
// isNarrow + prefersReducedMotion are REQUIRED (no defaults) so each
// variant passes them explicitly.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="activity-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Activity surface — emerald/teal orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof ActivityBackdrop> = {
  title: "Features/Activity/ActivityBackdrop",
  component: ActivityBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ActivityBackdrop>

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
