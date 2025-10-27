import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  darkMode: ["class", '[data-color-scheme="dark"]'],
  theme: {
    extend: {},
  },
  corePlugins: {
    preflight: false,
  },
}

export default config
