import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { useTranslation } from "react-i18next"
import { MobileDrawerQuickActions } from "./MobileDrawerQuickActions"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 360 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

/** Harness supplies the real i18next `t` from the preview I18nextProvider. */
function QuickActionsHarness() {
  const { t } = useTranslation()
  return (
    <MobileDrawerQuickActions
      onSearch={() => {}}
      onNotifications={() => {}}
      onSettings={() => {}}
      prefersReducedMotion={false}
      t={t}
    />
  )
}

const meta: Meta<typeof MobileDrawerQuickActions> = {
  title: "Navbar/MobileDrawerQuickActions",
  component: MobileDrawerQuickActions,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof MobileDrawerQuickActions>

export const Default: Story = { render: () => <QuickActionsHarness />, decorators: [themed(false)] }

export const DarkMode: Story = {
  render: () => <QuickActionsHarness />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
