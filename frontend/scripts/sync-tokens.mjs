import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Paths — Wave 112 SW2 fix: token sources live in BOTH `partials/` (legacy
// glass/motion primitives) and `tokens/` (feature-scoped activity/schedule/
// news/events/map token sheets). The old sync-tokens only read partials/
// which silently truncated `src/theme/tokens.ts` to a handful of exports on
// every `npm run build` (run-build.mjs calls sync-tokens before vite build).
const PARTIALS_DIR = path.resolve(__dirname, "../src/styles/partials")
const TOKENS_DIR = path.resolve(__dirname, "../src/styles/tokens")
const TOKENS_TS_PATH = path.resolve(__dirname, "../src/theme/tokens.ts")

console.log("🔄 Starting Token Synchronization...")

// 1. Parse CSS content to extract variables
function extractVariablesFromDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    console.error(`❌ Directory not found: ${dirPath}`)
    process.exit(1)
  }

  const files = fs.readdirSync(dirPath).filter((file) => file.endsWith(".css"))
  const variables = new Map()
  const variableRegex = /--([a-zA-Z0-9-]+):\s*([^;]+);/g

  files.forEach((file) => {
    const filePath = path.join(dirPath, file)
    const content = fs.readFileSync(filePath, "utf-8")
    let match
    while ((match = variableRegex.exec(content)) !== null) {
      const [, name, value] = match
      variables.set(name, value.trim())
    }
  })

  return variables
}
const themeVars = extractVariablesFromDir(PARTIALS_DIR)
if (fs.existsSync(TOKENS_DIR)) {
  const additional = extractVariablesFromDir(TOKENS_DIR)
  for (const [name, value] of additional) {
    // Later definitions win — matches CSS cascade order (tokens/ loaded after partials/).
    themeVars.set(name, value)
  }
  console.log(`✅ Found ${themeVars.size} CSS variables in partials/ + tokens/`)
} else {
  console.log(`✅ Found ${themeVars.size} CSS variables in ${PARTIALS_DIR}`)
}

// 2. Define Groups and their prefixes/logic
// This mapping defines which CSS variables go into which TS export object
const GROUPS = [
  {
    name: "spacingScale",
    pattern: /^space-/,
    transformKey: (k) => {
      // Map --space-1 to "2xs", etc. based on known mapping or keep raw if custom
      // For strict sync, we use the numeric suffix as key unless mapped manually
      const suffix = k.replace("space-", "")
      const manualMap = {
        1: "2xs",
        2: "xs",
        3: "sm",
        4: "md",
        6: "lg",
        8: "xl",
        12: "2xl",
        16: "3xl",
        32: "4xl",
      }
      return manualMap[suffix] || suffix
    },
    valueTransform: (k) => `var(--${k})`,
    // Also generate numeric keys for standard Tailwind spacing (e.g. "4": "var(--space-4)")
    extraKeysGenerator: (k) => {
      const suffix = k.replace("space-", "")
      // If suffix is numeric (including floating point like 0.5 -> 05 in name but 0.5 in tw),
      // we map it. Our tokens are named space-05, space-1, etc.
      // We want strict mapping: space-1 -> "1", space-05 -> "0.5"?
      // Actually, Tailwind uses "0.5", "1.5". Our vars are "05", "15".
      // Let's just map the exact suffix as a string key if it's numeric-ish.
      if (/^\d+(\.\d+)?$/.test(suffix) || /^\d+$/.test(suffix)) {
        return { key: suffix, value: `var(--${k})` }
      }
      return null
    },
  },
  {
    name: "radiusScale",
    pattern: /^radius-/,
    transformKey: (k) => {
      const suffix = k.replace("radius-", "")
      if (suffix === "full") return "pill"
      return suffix
    },
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "breakpoints",
    pattern: /^breakpoint-/, // Not currently in theme.css, handled below manually or via naming convention if added
    // If usage strictly follows manual breakpoints in tokens.ts, we might need to preserve them or add them to CSS.
    // Current CSS doesn't have --breakpoint-*. We will stick to the manual definition for now or generated if found.
    isManual: true,
  },
  {
    name: "zIndexTokens",
    pattern: /^z-/,
    transformKey: (k) => k.replace("z-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    // Wave 121 SW5: legacy --shadow-focus naming was never populated; new
    // --focus-ring-* primitives (default/thick/isolated) live in primitives.css.
    name: "focusRing",
    pattern: /^focus-ring-/,
    transformKey: (k) => k.replace("focus-ring-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "shadows",
    pattern: /^shadow-(sm|md|premium-lift|glass)$/, // Specific whitelist to match existing tokens.ts structure
    transformKey: (k) => k.replace("shadow-", "").replace("premium-lift", "lg"), // Map premium-lift to lg to match current tokens.ts
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "glass",
    pattern: /^glass-(bg|border|shadow|blur|tint3)$/,
    transformKey: (k) => k.replace("glass-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "fluidTypography",
    pattern: /^fs-fluid-(display|h1|h2|h3)$/,
    transformKey: (k) => k.replace("fs-fluid-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "dimensions",
    pattern: /^(h-hero|size-avatar|w-card|h-screen-offset)/,
    transformKey: (k) => {
      // Map to camelCase
      const parts = k.split("-")
      // e.g. h-hero-lg -> heroLg
      // e.g. h-screen-offset -> screenOffset
      // e.g. size-avatar-xl -> avatarXl
      // e.g. w-card-sm -> cardSm

      if (k.startsWith("h-hero")) {
        // Fix for h-hero-max-portrait etc.
        // parts: [h, hero, max, portrait] -> want heroMaxPortrait
        if (parts.length > 3) {
          return (
            "hero" +
            parts
              .slice(2)
              .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
              .join("")
          )
        }
        return "hero" + parts[2].charAt(0).toUpperCase() + parts[2].slice(1)
      }
      if (k === "h-screen-offset") return "screenOffset"
      if (k.startsWith("size-avatar"))
        return "avatar" + parts[2].charAt(0).toUpperCase() + parts[2].slice(1)
      if (k.startsWith("w-card"))
        return "card" + parts[2].charAt(0).toUpperCase() + parts[2].slice(1)
      return k
    },
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "opacity",
    pattern: /^opacity-/,
    transformKey: (k) => k.replace("opacity-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "scale",
    pattern: /^scale-hover$/,
    transformKey: () => "hover",
    valueTransform: (k) => `var(--${k})`,
    // 'active' is statically defined in tokens.ts as 0.98 usually
    extraKeys: { active: "0.98" },
  },
  {
    name: "motion",
    pattern: /^motion-/,
    transformKey: (k) => {
      // Map css vars to legacy token names
      const suffix = k.replace("motion-", "")
      // Special mappings to match existing tokens.ts
      if (suffix === "stagger-medium") return "staggerDelay"
      if (suffix === "duration-fast") return "durationFast"
      if (suffix === "duration-medium") return "durationMedium"
      if (suffix === "nav-transition") return "navTransition"

      // Convert kebab-case to camelCase for others
      return suffix.replace(/-./g, (x) => x[1].toUpperCase())
    },
    valueTransform: (k, value) => {
      // If the value is a time string (e.g. 0.2s), parse it to a number
      if (typeof value === "string" && value.endsWith("s")) {
        const num = parseFloat(value)
        if (!isNaN(num)) return num
      }
      return value
    },
    // We want raw values, not var(--...) wrappers for these numbers
    raw: true,
  },
  {
    name: "icon",
    pattern: /^size-icon-/,
    transformKey: (k) => k.replace("size-icon-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
  {
    name: "letterSpacing",
    pattern: /^tracking-/,
    transformKey: (k) => k.replace("tracking-", ""),
    valueTransform: (k) => `var(--${k})`,
  },
]

// 3. Generate Content
let output = `// -----------------------------------------------------------------------------
// TOKENS.TS
// -----------------------------------------------------------------------------
// This file is a strict TypeScript mirror of the CSS variables defined in
// \`src/styles/theme.css\`. It is used for JS-based styling (e.g., Framer Motion).
//
// ⚠️  WARNING: DO NOT EDIT VALUES HERE MANUALLY.
//     Always update \`src/styles/theme.css\` first, then run \`npm run tokens:sync\`.
// -----------------------------------------------------------------------------

`

GROUPS.forEach((group) => {
  if (group.name === "breakpoints") {
    // Breakpoints manual block
    output += `export const breakpoints = {
  small: "640px",
  mobile: "768px",
  content: "900px",
  tablet: "1024px",
  dashboard: "1100px",
  storiesInHero: "1220px",
  desktop: "1280px",
  wide: "1350px",
  ultrawide: "1730px",
} as const\n\n`
    return
  }

  const entries = []

  // Find matching vars
  for (const [key, rawValue] of themeVars.entries()) {
    if (group.pattern.test(key)) {
      const jsKey = group.transformKey(key)
      if (jsKey) {
        let jsValue
        if (group.raw) {
          // Pass the raw value from map (e.g. "0.2s") to transform
          jsValue = group.valueTransform(key, rawValue)
        } else {
          jsValue = group.valueTransform(key)
        }

        // Check if key already exists to prevent duplicates
        if (!entries.some((e) => e.key === jsKey)) {
          entries.push({ key: jsKey, value: jsValue })
        }
      }
    }
  }

  // Add extras
  if (group.extraKeys) {
    Object.entries(group.extraKeys).forEach(([k, v]) => {
      if (!entries.some((e) => e.key === k)) {
        entries.push({ key: k, value: v })
      }
    })
  }

  // Add generated extra keys (new feature)
  if (group.extraKeysGenerator) {
    for (const [key] of themeVars.entries()) {
      if (group.pattern.test(key)) {
        const extra = group.extraKeysGenerator(key)
        if (extra) {
          // Only add if not already present
          if (!entries.some((e) => e.key === extra.key)) {
            entries.push(extra)
          }
        }
      }
    }
  }

  // Sort for stability
  entries.sort((a, b) => a.key.localeCompare(b.key))

  if (entries.length === 0) {
    output += `export const ${group.name} = {} as const\n\n`
  } else {
    output += `export const ${group.name} = {\n`

    entries.forEach(({ key, value }) => {
      // Quote keys if they start with number or invalid chars
      const safeKey = /^[a-zA-Z_$][a-zA-Z0-9_$]*$/.test(key) ? key : `"${key}"`

      // If value is a string, quote it. If number, don't.
      if (typeof value === "string") {
        output += `  ${safeKey}: "${value}",\n`
      } else {
        output += `  ${safeKey}: ${value},\n`
      }
    })

    output += `} as const\n\n`
  }
})

// 4. Write File
fs.writeFileSync(TOKENS_TS_PATH, output.trim() + "\n", "utf-8")
console.log(`✅ Generated tokens.ts at ${TOKENS_TS_PATH}`)
console.log("✨ Token synchronization complete.")
