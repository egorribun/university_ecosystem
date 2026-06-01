import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { weatherQueryKey } from "@/api/hooks/weather"
import { CAMPUS_COORDINATES } from "@/constants/campus"
import type { WeatherSnapshot } from "@/api/weather"
import WeatherWidget from "./WeatherWidget"

// Wave 199 SW1 — WeatherWidget story (CONTEXT-tier, no infra).
//
// Renders null until useWeather() resolves, so the story seeds a per-story
// QueryClient at weatherQueryKey(CAMPUS_COORDINATES) with a WeatherSnapshot
// (W198 NewChatModal seeding pattern). With refetchOnMount:false + a fresh
// staleTime, the widget paints the seeded data without a network round-trip and
// derives the icon/animation from conditionCode. No portal, no framer-motion.
//
// Variants: Default / DarkMode.

const SNAPSHOT: WeatherSnapshot = {
  conditionCode: 1,
  conditionLabel: "Mainly clear",
  temperatureC: 18,
  observedAt: new Date().toISOString(),
}

const seededClient = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(weatherQueryKey(CAMPUS_COORDINATES), SNAPSHOT)
  return client
}

const seeded: Decorator = (Story) => (
  <QueryClientProvider client={seededClient()}>
    <Story />
  </QueryClientProvider>
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof WeatherWidget> = {
  title: "UI/WeatherWidget",
  component: WeatherWidget,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof WeatherWidget>

export const Default: Story = { decorators: [themed(false), seeded] }

export const DarkMode: Story = {
  decorators: [themed(true), seeded],
  parameters: { backgrounds: { default: "dark" } },
}
