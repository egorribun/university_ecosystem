import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { OtpEntry } from "./OtpEntry"

// Wave 196 SW2 — OtpEntry Storybook fixture (LEAF tier batch 2).
//
// Six-digit TOTP authenticator-code entry (paste-aware, keyboard nav, auto-submit
// on 6 digits). Renders from props alone (loading/error/helperText/onSubmit);
// labels come from the global I18nextProvider. No framer-motion (CSS-only
// animations) → no LazyMotion; no theme scope (global brand tokens). `Auth/`
// group matches the W194 MfaChallengeView precedent.
//
// Variants: Default (empty) / Loading (spinner) / Error (shake banner) / WithHelper.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem", maxWidth: 420 }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof OtpEntry> = {
  title: "Auth/OtpEntry",
  component: OtpEntry,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof OtpEntry>

export const Default: Story = {
  args: { onSubmit: () => {} },
  decorators: [themed(false)],
}

export const Loading: Story = {
  args: { loading: true, onSubmit: () => {} },
  decorators: [themed(false)],
}

export const Error: Story = {
  args: { error: "Invalid code. Please try again.", onSubmit: () => {} },
  decorators: [themed(false)],
}

export const WithHelper: Story = {
  args: {
    helperText: "Enter the 6-digit code from your authenticator app.",
    onSubmit: () => {},
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { onSubmit: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
