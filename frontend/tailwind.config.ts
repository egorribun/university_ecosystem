import plugin from "tailwindcss/plugin"
import lineClamp from "@tailwindcss/line-clamp"
import type { Config } from "tailwindcss"

const attributeSelector = (attribute: "data" | "aria", value: string) => {
  const [rawAttr, rawValue] = value.split("=")
  const attr = rawAttr?.trim()
  const attrValue = rawValue?.trim()

  if (!attr) {
    return ""
  }

  return attrValue ? `[${attribute}-${attr}="${attrValue}"]` : `[${attribute}-${attr}="true"]`
}

const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        page: {
          DEFAULT: "var(--page-bg)",
          foreground: "var(--page-text)",
        },
        surface: {
          DEFAULT: "var(--card-bg)",
          accent: "var(--option-hover-bg)",
        },
        nav: {
          DEFAULT: "var(--nav-bg)",
          text: "var(--nav-text)",
          link: "var(--nav-link)",
          hover: "var(--nav-link-hover)",
        },
        button: {
          DEFAULT: "var(--btn-bg)",
          border: "var(--btn-border)",
        },
        secondary: "var(--secondary-text)",
        glass: {
          DEFAULT: "var(--glass-bg)",
          border: "var(--glass-border)",
          highlight: "var(--glass-highlight)",
          tint1: "var(--glass-tint-1)",
          tint2: "var(--glass-tint-2)",
          tint3: "var(--glass-tint-3)",
        },
        progress: {
          track: "var(--progress-track)",
          bar: "var(--progress-bar)",
        },
        slate: {
          5: "var(--slate-05)",
          10: "var(--slate-10)",
          20: "var(--slate-20)",
          40: "var(--slate-40)",
        },
        hint: "var(--hint-fg)",
        placeholder: "var(--placeholder-fg)",
      },
      backgroundImage: {
        "hero-gradient":
          "linear-gradient(100deg,var(--hero-grad-start) 40%,var(--hero-grad-end) 100%)",
        "hero-gradient-strong":
          "linear-gradient(100deg,var(--hero-grad-start) 50%,var(--hero-grad-end) 100%)",
        "btn-gradient":
          "linear-gradient(98deg,var(--fed-blue-60v) 10%,var(--fed-blue-70v) 55%,var(--fed-blue-80v) 100%)",
        "btn-gradient-hover":
          "linear-gradient(98deg,var(--fed-blue-70v) 8%,#3e78b2 55%,#69a9dc 100%)",
        skeleton:
          "linear-gradient(180deg,var(--slate-05) 0%,var(--slate-10) 50%,var(--slate-05) 100%)",
      },
      boxShadow: {
        surface: "var(--shadow-1)",
        "surface-strong": "var(--shadow-2)",
        focus: "var(--shadow-focus)",
        "focus-ring": "var(--ue-focus-ring)",
        glass: "var(--glass-shadow)",
      },
      borderRadius: {
        surface: "var(--radius-md)",
        "surface-lg": "var(--radius-lg)",
        "ue-xs": "var(--ue-radius-xs)",
        "ue-sm": "var(--ue-radius-sm)",
        "ue-md": "var(--ue-radius-md)",
        "ue-lg": "var(--ue-radius-lg)",
        "ue-xl": "var(--ue-radius-xl)",
        "ue-pill": "var(--ue-radius-pill)",
      },
      spacing: {
        "ue-2xs": "var(--ue-spacing-2xs)",
        "ue-xs": "var(--ue-spacing-xs)",
        "ue-sm": "var(--ue-spacing-sm)",
        "ue-md": "var(--ue-spacing-md)",
        "ue-lg": "var(--ue-spacing-lg)",
        "ue-xl": "var(--ue-spacing-xl)",
      },
      fontFamily: {
        ui: ["var(--font-ui)"],
        display: ["var(--font-display)"],
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(0.25rem)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "card-hover": {
          "0%": {
            transform: "translateY(0) scale(1)",
            boxShadow: "var(--shadow-1)",
          },
          "100%": {
            transform: "translateY(-2px) scale(1.03)",
            boxShadow: "var(--shadow-2)",
          },
        },
        "skeleton-wave": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "aura-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(255,255,255,0.18)" },
          "50%": { boxShadow: "0 0 0 14px rgba(255,255,255,0.03)" },
          "100%": { boxShadow: "0 0 0 0 rgba(255,255,255,0.02)" },
        },
        "chip-highlight": {
          "0%": { borderColor: "rgba(255,255,255,0.18)" },
          "50%": { borderColor: "rgba(255,255,255,0.34)" },
          "100%": { borderColor: "rgba(255,255,255,0.18)" },
        },
        "online-pulse": {
          "0%": { transform: "scale(1)", opacity: "0.6" },
          "70%": { transform: "scale(1.8)", opacity: "0" },
          "100%": { transform: "scale(1.8)", opacity: "0" },
        },
      },
      animation: {
        "fade-in": "fade-in var(--anim-med, 0.3s cubic-bezier(0.42, 0, 0.58, 1)) both",
        "card-hover": "card-hover var(--anim-card, 0.42s cubic-bezier(0.22, 0.61, 0.36, 1)) both",
        "skeleton-wave": "skeleton-wave 1.6s ease-in-out infinite",
        "aura-pulse": "aura-pulse 14s ease-in-out infinite",
        "chip-highlight": "chip-highlight 12s ease-in-out infinite",
        "online-pulse": "online-pulse 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [
    plugin(({ addVariant, matchVariant }) => {
      addVariant("supports-scroll", "@supports (scroll-behavior: smooth)")

      matchVariant("data", (value) => {
        const selector = attributeSelector("data", value)
        return selector ? `&${selector}` : "&"
      })

      matchVariant("aria", (value) => {
        const selector = attributeSelector("aria", value)
        return selector ? `&${selector}` : "&"
      })

      matchVariant("group-data", (value) => {
        const selector = attributeSelector("data", value)
        return selector ? `.group${selector} &` : ".group &"
      })

      matchVariant("group-aria", (value) => {
        const selector = attributeSelector("aria", value)
        return selector ? `.group${selector} &` : ".group &"
      })

      matchVariant("peer-data", (value) => {
        const selector = attributeSelector("data", value)
        return selector ? `.peer${selector} ~ &` : ".peer ~ &"
      })

      matchVariant("peer-aria", (value) => {
        const selector = attributeSelector("aria", value)
        return selector ? `.peer${selector} ~ &` : ".peer ~ &"
      })
    }),
    lineClamp,
  ],
}

export default config
