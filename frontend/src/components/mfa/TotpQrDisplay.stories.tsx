import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { TotpQrDisplay } from "./TotpQrDisplay"

// Wave 196 SW2 — TotpQrDisplay Storybook fixture (LEAF tier batch 2).
//
// TOTP enrolment view: QR code (lazy qrcode.react via Suspense) + copyable manual
// secret. Renders from props alone (otpauthUrl/secret/label). No framer-motion,
// no theme scope. The secret below is a repetitive low-entropy placeholder (NOT a
// real key) so detect-secrets stays quiet; the QR fg/bg colors are hardcoded
// high-contrast by design (scanner reliability). `Auth/` group.
//
// Variants: Default (with account label) / NoLabel.

const DEMO_SECRET = "JBSWJBSWJBSWJBSW" // pragma: allowlist secret -- demo TOTP seed (not a real key)
const DEMO_OTPAUTH = `otpauth://totp/GUU:student@guu.ru?secret=${DEMO_SECRET}&issuer=GUU`

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

const meta: Meta<typeof TotpQrDisplay> = {
  title: "Auth/TotpQrDisplay",
  component: TotpQrDisplay,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof TotpQrDisplay>

export const Default: Story = {
  args: { otpauthUrl: DEMO_OTPAUTH, secret: DEMO_SECRET, label: "student@guu.ru" },
  decorators: [themed(false)],
}

export const NoLabel: Story = {
  args: { otpauthUrl: DEMO_OTPAUTH, secret: DEMO_SECRET },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { otpauthUrl: DEMO_OTPAUTH, secret: DEMO_SECRET, label: "student@guu.ru" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
