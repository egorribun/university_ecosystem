import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { AuthBackdrop } from "./AuthBackdrop"

// Wave 193 SW3 — AuthBackdrop Storybook fixture.
//
// 3-prop family (isNarrow + isMobile + prefersReducedMotion, all optional;
// `dropBlur = prefersReducedMotion || isMobile`). Teal/cyan ambient orbs
// scoped under `.auth-theme` (tokens/auth.css), so the `themed(dark)`
// decorator factory (W193 SW2 pattern) wraps the backdrop in `.auth-theme`
// with `.dark` as an ANCESTOR for the dark variant. Production wrappers:
// Login.tsx:80, Register.tsx:156, ForgotPassword.tsx:95, ResetPassword.tsx:158
// (AuthBackdrop coexists with ParticleAuthBackground on Login + Register).
//
// Variants: Default / DarkMode / Narrow (tablet: narrow orbs, blur KEPT) /
// ReducedMotion (drops drifting conic) / Mobile (phone: narrow orbs, blur
// DROPPED via isMobile — the tablet-vs-phone GPU distinction).

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="auth-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Auth surface — teal/cyan orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof AuthBackdrop> = {
  title: "Auth/AuthBackdrop",
  component: AuthBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof AuthBackdrop>

export const Default: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
    prefersReducedMotion: false,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: {
    isNarrow: false,
    isMobile: false,
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
    isMobile: false,
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
    isMobile: false,
    prefersReducedMotion: true,
  },
  decorators: [themed(false)],
}

export const Mobile: Story = {
  args: {
    isNarrow: true,
    isMobile: true,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
  decorators: [themed(false)],
}
