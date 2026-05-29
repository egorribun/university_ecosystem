import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import Navbar from "./Navbar"

// Wave 199 SW1 — Navbar integration story (CONTEXT-tier, no infra).
//
// Zero-prop sticky navbar. Drives itself entirely from ambient providers:
// useNavbarLogic + useNavbarMorph read useAuth (mock admin via preview.tsx
// AuthContext), useRouterState (preview RouterProvider, pathname "/"), and
// i18n. At desktop width it renders the DesktopNav pill + UserMenu (the
// NavbarLogo + NavbarActions + NavbarPill + MobileMenu sub-pieces are storied
// individually in W198). Uses framer-motion `m.*` → LazyMotion required.
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div style={{ background: "var(--bg-page)", minHeight: 320 }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof Navbar> = {
  title: "Navbar/Navbar",
  component: Navbar,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Navbar>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
