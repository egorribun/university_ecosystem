import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { useNavbarLogic } from "./useNavbarLogic"
import { useNavbarMorph } from "./useNavbarMorph"
import { NavbarActions } from "./NavbarActions"

// Wave 199 SW1 — NavbarActions story (CONTEXT-tier, no infra).
//
// NavbarActions takes a full `NavbarLogicResult` + `NavbarMorphState` (~25
// fields). Rather than hand-mock that surface, the harness calls the REAL
// useNavbarLogic + useNavbarMorph (satisfied by the ambient AuthContext /
// RouterProvider / i18n from preview.tsx) and passes them through — same
// real-provider approach W197 used for context-coupled components. At desktop
// width this renders DesktopNav + UserMenu (the actions row in isolation).
// Uses framer-motion `m.*` → LazyMotion required.
//
// Variants: Default / DarkMode.

const NavbarActionsHarness = () => {
  const logic = useNavbarLogic()
  const morph = useNavbarMorph(logic.menuLinks)
  return <NavbarActions logic={logic} morph={morph} />
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          style={{ background: "var(--bg-page)", padding: "2rem", display: "flex", gap: "0.75rem" }}
        >
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NavbarActions> = {
  title: "Navbar/NavbarActions",
  component: NavbarActions,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  render: () => <NavbarActionsHarness />,
}

export default meta
type Story = StoryObj<typeof NavbarActions>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
