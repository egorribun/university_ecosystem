import type { Meta, StoryObj } from "@storybook/react-vite"
import Footer from "./Footer"

// Wave 176 SW5 — Footer Storybook fixture.
// Global preview decorator (`.storybook/preview.tsx`) supplies TanStack
// Router + I18nextProvider + LanguageProvider + AuthContext + global
// Tailwind CSS — Footer renders unwrapped here.
//
// Variants:
//   • Default — light theme (preview backgrounds default)
//   • DarkMode — adds `dark` class on body via decorator, uses dark
//     backgrounds parameter
//   • Narrow — emulates ≤900px viewport (matches breakpoints.content used
//     by Footer's `useMediaQuery` hook → FooterBackdrop's `isNarrow` prop
//     triggers smaller orb dimensions). Container queries (`@sm`/`@lg`)
//     also collapse columns from 5→2→1.
//   • ReducedMotion — entrance + stagger + orb blur drop via OS preference
//     simulation (Tailwind `motion-reduce:` + CSS @media)

const meta: Meta<typeof Footer> = {
  title: "Layout/Footer",
  component: Footer,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Footer>

export const Default: Story = {}

export const DarkMode: Story = {
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
}

export const Narrow: Story = {
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
}

/**
 * ActiveDot story — demonstrates the W176 SW4 active-route indicator.
 * Synthetically injects `data-status="active"` on the /news link via the
 * `play` function (Storybook interactions API). Real TanStack Router auto-
 * applies this attribute when the current pathname matches; this story
 * visualises the CSS without needing a real Router context to navigate.
 *
 * Storybook can't truly flip OS `prefers-reduced-motion` so a dedicated
 * ReducedMotion story would be no-op. Real reduced-motion behaviour is
 * exercised via `tests/e2e/a11y-public.spec.ts` `emulateMedia({
 * reducedMotion: 'reduce' })` (Wave 114 SW2b) + the `motion-reduce:`
 * Tailwind variants on the footer container itself.
 */
export const ActiveDot: Story = {
  play: async ({ canvasElement }) => {
    const newsLink = canvasElement.querySelector('a.footer-link-premium[href="/news"]')
    if (newsLink) newsLink.setAttribute("data-status", "active")
    const profileLink = canvasElement.querySelector('a.footer-link-premium[href="/profile"]')
    if (profileLink) profileLink.setAttribute("data-status", "active")
  },
}
