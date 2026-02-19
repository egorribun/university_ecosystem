/* eslint-env node */
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Paths
const THEME_CSS_PATH = path.resolve(__dirname, "../src/styles/theme.css")
const TOKENS_TS_PATH = path.resolve(__dirname, "../src/theme/tokens.ts")

console.log("🔄 Starting Token Synchronization...")

// 1. Parse CSS content to extract variables
function extractCssVariables(filePath, visited = new Set()) {
  const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(path.dirname(entryPath), filePath)

  // Prevent cycles
  if (visited.has(absolutePath)) return new Map()
  visited.add(absolutePath)

  if (!fs.existsSync(absolutePath)) {
    console.warn(`⚠️  File not found: ${absolutePath}`)
    return new Map()
  }

  const content = fs.readFileSync(absolutePath, "utf-8")
  const dir = path.dirname(absolutePath)
  const variables = new Map()

  // 1. Handle Imports
  const importRegex = /@import\s+["']([^"']+)["'];/g
  let importMatch
  while ((importMatch = importRegex.exec(content)) !== null) {
    const importPath = importMatch[1]
    const resolvedImport = path.resolve(dir, importPath)
    const importedVars = extractCssVariables(resolvedImport, visited)
    importedVars.forEach((v, k) => variables.set(k, v))
  }

  // 2. Extract Variables
  const variableRegex = /--([a-zA-Z0-9-]+):\s*([^;]+);/g
  let match
  while ((match = variableRegex.exec(content)) !== null) {
    const [_, name, value] = match
    variables.set(name, value.trim())
  }
  return variables
}
// Store entry path for relative resolution context if needed,
// strictly speaking recursion handles it if we pass absolute paths.
// But initial call needs to be correct.
const entryPath = THEME_CSS_PATH

const themeVars = extractCssVariables(THEME_CSS_PATH)
console.log(`✅ Found ${themeVars.size} CSS variables in theme.css`)

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
    extraKeysGenerator: (k, v) => {
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
    name: "focusRing",
    pattern: /^shadow-focus/,
    transformKey: () => "default",
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
    // Motion vars are not fully in CSS yet, mostly hardcoded in tokens.ts.
    // We will preserve the static block for now or look for specific vars if they exist.
    isManual: true,
    staticContent: `  staggerDelay: 0.06,
  durationFast: 0.2,
  durationMedium: 0.45,
  navTransition: 1.2,`,
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
  desktop: "1280px",
  wide: "1350px",
  ultrawide: "1730px",
} as const\n\n`
    return
  }

  if (group.name === "motion") {
    output += `export const motion = {
${group.staticContent}
} as const\n\n`
    return
  }

  output += `export const ${group.name} = {\n`

  const entries = []

  // Find matching vars
  for (const [key, _] of themeVars.entries()) {
    if (group.pattern.test(key)) {
      const jsKey = group.transformKey(key)
      if (jsKey) {
        const jsValue = group.valueTransform(key)
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
    for (const [key, _] of themeVars.entries()) {
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

  entries.forEach(({ key, value }) => {
    // Quote keys if they start with number or invalid chars
    const safeKey = /^[a-zA-Z_$][a-zA-Z0-9_$]*$/.test(key) ? key : `"${key}"`
    output += `  ${safeKey}: "${value}",\n`
  })

  output += `} as const\n\n`
})

// 4. Write File
fs.writeFileSync(TOKENS_TS_PATH, output, "utf-8")
console.log(`✅ Generated tokens.ts at ${TOKENS_TS_PATH}`)
console.log("✨ Token synchronization complete.")
