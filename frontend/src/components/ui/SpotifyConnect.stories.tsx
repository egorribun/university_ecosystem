import { useEffect, type ReactNode } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { useAuthStore } from "@/stores/useAuthStore"
import type { User } from "@/types/User"
import SpotifyConnect from "./SpotifyConnect"

// Wave 199 SW1 — SpotifyConnect story (CONTEXT-tier, no infra).
//
// `useAuth().user` reads the Zustand store (NOT the AuthContext), which
// Storybook doesn't populate → `if (!user) return null`. The StoreSeed harness
// seeds useAuthStore in an effect (a render-phase `useAuthStore.setState` trips
// the React Compiler — `use*`-namespace member access, W128 SW1 class — at
// build time, not just lint) and resets it on unmount, so SpotifyConnect renders
// the connect / connected UI. `spotify_connected` drives the variant.
// useNowPlaying is enabled-gated on connection + fails gracefully (no track
// card) without a backend. Wrapped in `.settings-theme`.
//
// Variants: NotConnected / Connected / DarkMode.

const baseUser: User = {
  id: "u1",
  email: "egor@guu.ru",
  full_name: "Егор Студентов",
  role: "student",
  avatar_url: null,
  mfa_required: false,
  is_active: true,
  avatar_url_optimized: null,
  cover_url_optimized: null,
}

const StoreSeed = ({ user, children }: { user: User; children: ReactNode }) => {
  // Seed inside the effect (NOT render) so the React Compiler doesn't flag the
  // `useAuthStore.setState` reference. First paint sees user=null (SpotifyConnect
  // renders null), the effect then seeds the store → re-render shows the content.
  useEffect(() => {
    useAuthStore.setState({ user, loading: false })
    return () => useAuthStore.setState({ user: null })
  }, [user])
  return <>{children}</>
}

const themed = (dark: boolean, user: User): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="settings-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 480 }}>
            <StoreSeed user={user}>
              <Story />
            </StoreSeed>
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const notConnected: User = { ...baseUser, spotify_connected: false }
const connected: User = { ...baseUser, spotify_connected: true, spotify_display_name: "egor.music" }

const meta: Meta<typeof SpotifyConnect> = {
  title: "UI/SpotifyConnect",
  component: SpotifyConnect,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof SpotifyConnect>

export const NotConnected: Story = { decorators: [themed(false, notConnected)] }

export const Connected: Story = { decorators: [themed(false, connected)] }

export const DarkMode: Story = {
  decorators: [themed(true, connected)],
  parameters: { backgrounds: { default: "dark" } },
}
