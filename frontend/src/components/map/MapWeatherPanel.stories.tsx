import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MapWeatherPanel } from "./MapWeatherPanel"
import type { MapWeatherData } from "@/hooks/useMapWeather"

// Wave 196 SW1 — MapWeatherPanel Storybook fixture (LEAF tier batch 2).
//
// Expanded weather panel (feels-like / wind / humidity / UV + 12h hourly
// forecast). Controlled via `data` + `open` + `onClose` props — the MapWeatherBadge
// owns the `useMapWeather()` call and feeds the resolved data DOWN to this panel,
// so the panel itself is a clean prop-driven LEAF (the badge is NOT — it returns
// null without hook data, hence SKIP). Uses framer-motion `m.*` + AnimatePresence
// → LazyMotion. `.map-theme` supplies `.map-weather-panel` tokens. The panel is
// position:absolute, so the decorator gives it a `relative` host with height.
// `pauseAnimationAtEnd` freezes the entrance for Chromatic.
//
// Variants: Default (clear day) / Night (Moon icon) / DarkMode.

const weatherData: MapWeatherData = {
  temperature: 18,
  weatherCode: 1,
  isDay: true,
  condition: "clear",
  feelsLike: 17,
  windSpeed: 3,
  humidity: 62,
  uvIndex: 4,
  hourlyForecast: [
    { hour: 9, temperature: 16, condition: "clear" },
    { hour: 10, temperature: 18, condition: "clear" },
    { hour: 11, temperature: 19, condition: "cloudy" },
    { hour: 12, temperature: 20, condition: "cloudy" },
    { hour: 13, temperature: 21, condition: "rain" },
    { hour: 14, temperature: 20, condition: "rain" },
  ],
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="map-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ position: "relative", width: 320, minHeight: 360 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MapWeatherPanel> = {
  title: "Map/MapWeatherPanel",
  component: MapWeatherPanel,
  parameters: {
    layout: "centered",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapWeatherPanel>

export const Default: Story = {
  args: { data: weatherData, open: true, onClose: () => {} },
  decorators: [themed(false)],
}

export const Night: Story = {
  args: { data: { ...weatherData, isDay: false }, open: true, onClose: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { data: { ...weatherData, isDay: false }, open: true, onClose: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
