import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { LoginHero } from "./LoginHero"

// Wave 199 SW1 — LoginHero Storybook fixture (CONTEXT-tier, no infra).
//
// Zero-prop marketing hero panel for the login page. Pure i18n render
// (useTranslation(["auth"])) — no network, no portal. Wraps content in FadeIn
// (framer-motion `m.*`) → LazyMotion required. `auth-card-glass` is a GLOBAL
// @utility (tailwind.css), but the panel is wrapped in `.auth-theme` to match
// the real auth surface + provide the teal/cyan token context.
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="auth-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ maxWidth: 680 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof LoginHero> = {
  title: "Auth/LoginHero",
  component: LoginHero,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof LoginHero>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
