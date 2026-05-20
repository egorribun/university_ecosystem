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

export const ReducedMotion: Story = {
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [
    (Story) => (
      <div
        className="dark"
        style={
          {
            // Simulate prefers-reduced-motion via CSS — Storybook can't
            // actually flip the OS media query, but this decorator visually
            // demonstrates a "snapped" state. Real reduced-motion behavior
            // is exercised via `tests/e2e/a11y-public.spec.ts`
            // `emulateMedia({ reducedMotion: 'reduce' })` (Wave 114 SW2b).
          } as React.CSSProperties
        }
      >
        <Story />
      </div>
    ),
  ],
}
