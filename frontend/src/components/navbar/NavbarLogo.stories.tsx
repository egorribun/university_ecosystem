import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { useTranslation } from "react-i18next"
import { NavbarLogo } from "./NavbarLogo"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{
          background: "var(--bg-page)",
          padding: "2rem",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

/** Harness supplies the real i18next `t` (TFunction) from the preview I18nextProvider. */
function LogoHarness({ isCompact = false, isMobile = false, isPhone = false }) {
  const { t } = useTranslation()
  return (
    <NavbarLogo
      t={t}
      isMobile={isMobile}
      isCompact={isCompact}
      isPhone={isPhone}
      prefersReducedMotion={false}
      onLogoClick={() => {}}
      markScrollFromBottom={() => {}}
    />
  )
}

const meta: Meta<typeof NavbarLogo> = {
  title: "Navbar/NavbarLogo",
  component: NavbarLogo,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    // logo-shimmer sweep animation — freeze for Chromatic.
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof NavbarLogo>

export const Expanded: Story = { render: () => <LogoHarness />, decorators: [themed(false)] }

export const Compact: Story = {
  render: () => <LogoHarness isCompact />,
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Compact — brand text collapses, logo circle shrinks." } },
  },
}

export const DarkMode: Story = {
  render: () => <LogoHarness />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
