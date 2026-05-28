import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { AdminBackdrop } from "./AdminBackdrop"

// Wave 193 SW2 — AdminBackdrop Storybook fixture.
//
// Co-located under `src/features/admin/` — only discoverable since the
// W193 SW1 glob widen (`../src/features/**`). Together with
// ActivityBackdrop.stories.tsx, proves the widen end-to-end.
//
// Same `themed(dark)` factory as ActivityBackdrop.stories.tsx: AdminBackdrop's
// orb tokens (`--admin-hero-orb`, `--admin-hero-highlight`,
// `--grad-admin-conic`, `--admin-orb-3`) are SCOPE-defined under
// `.admin-theme` (tokens/admin.css:42 light + :121 dark), so the decorator
// must wrap in `.admin-theme` with `.dark` as an ANCESTOR for the dark
// variant. Production wrapper: AdminLayout in routes/_admin.tsx:43.
//
// Variants: Default / DarkMode / Narrow (drops desktop highlight + conic) /
// ReducedMotion (drops the drifting conic). Props isNarrow +
// prefersReducedMotion are REQUIRED (no defaults) — passed explicitly.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="admin-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Admin surface — indigo/slate orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof AdminBackdrop> = {
  title: "Features/Admin/AdminBackdrop",
  component: AdminBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof AdminBackdrop>

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
