/**
 * Wave 191 SW3 — Hook migration regression test (W184 SW6 + W190 broader sweep).
 *
 * ## Why this exists
 *
 * W184 SW6 discovered framer-motion's `useReducedMotion()` is jsdom-incompatible
 * — it touches `window.matchMedia(...).addEventListener` via
 * `initPrefersReducedMotion` through a code path jsdom's polyfill doesn't fully
 * cover, producing `TypeError: Cannot read properties of undefined (reading
 * 'addEventListener')` as vitest unhandled errors.
 *
 * W190 broader migration sweep closed all 25/25 component+hook source-level
 * imports of `useReducedMotion` from `framer-motion` (pre-W190 grep returned
 * 25 matches; post-W190 returns 0). The canonical replacement is the project's
 * own `useMediaQuery("(prefers-reduced-motion: reduce)")` hook (DEFAULT export
 * from `@/hooks/useMediaQuery`).
 *
 * This test is a **belt-and-suspenders regression guard** against:
 *
 * 1. New code being added that re-imports `useReducedMotion` from framer-motion
 *    (the W191 SW3 ESLint `no-restricted-imports` rule catches this at lint
 *    time; this test catches it at vitest time if the lint rule is ever
 *    disabled / removed)
 *
 * 2. The ESLint rule itself being deleted / weakened (vitest is independent of
 *    eslint.config.mjs state)
 *
 * ## Method
 *
 * Filesystem-level grep using glob 11.x to scan all `frontend/src/**\/*.{ts,tsx}`
 * source files. Match BOTH import patterns from W190 SW1-SW4 migration:
 *
 *   Pattern A (combined siblings):
 *     import { AnimatePresence, m, useReducedMotion } from "framer-motion"
 *
 *   Pattern B (sole import):
 *     import { useReducedMotion } from "framer-motion"
 *
 * Regex `/import\s*\{[^}]*\buseReducedMotion\b[^}]*\}\s*from\s*["']framer-motion["']/`
 * captures both — the `[^}]*` inside `{...}` allows any other named imports
 * before/after `useReducedMotion`, and `\b...\b` ensures word-boundary match
 * (so a hypothetical `useReducedMotionAlias` wouldn't false-trigger).
 *
 * ## Excluded
 *
 * Test files (`src/tests/**` + `**\/__tests__/**` + `*.test.ts(x)` + `*.spec.ts(x)`)
 * are excluded because:
 *
 * 1. Some test files have `vi.mock("framer-motion", () => ({ useReducedMotion:
 *    () => false, ... }))` stubs which are legitimate (mocking the framer-motion
 *    module to return a stable jsdom-safe value for the components under test).
 *
 * 2. This regression test itself uses the string `useReducedMotion` extensively
 *    in comments + the regex — excluding tests prevents self-match.
 *
 * If real production source code is added that imports `useReducedMotion` from
 * framer-motion, this test will fail with a clear list of violating files.
 */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"
import { glob } from "glob"
import { describe, expect, it } from "vitest"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SRC_ROOT = path.resolve(__dirname, "..")

// Captures both Pattern A (combined siblings) + Pattern B (sole import) per
// W190 SW1-SW4 migration recipes. `\b...\b` word-boundary prevents
// `useReducedMotionAlias` false-positives.
const FRAMER_MOTION_USE_REDUCED_MOTION_RE =
  /import\s*\{[^}]*\buseReducedMotion\b[^}]*\}\s*from\s*["']framer-motion["']/

describe("Hook migration regression — W184 SW6 + W190 broader sweep", () => {
  it("no production source file imports useReducedMotion from framer-motion", async () => {
    const files = await glob("**/*.{ts,tsx}", {
      cwd: SRC_ROOT,
      ignore: [
        "tests/**", // src/tests/ — this test file + helpers + integration tests
        "**/__tests__/**", // co-located component test directories
        "**/*.test.{ts,tsx}", // any *.test.ts / *.test.tsx anywhere
        "**/*.spec.{ts,tsx}", // any *.spec.ts / *.spec.tsx anywhere
      ],
    })

    const violations: string[] = []
    for (const relFile of files) {
      const fullPath = path.join(SRC_ROOT, relFile)
      const src = readFileSync(fullPath, "utf-8")
      if (FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(src)) {
        violations.push(relFile)
      }
    }

    expect(
      violations,
      `Files importing useReducedMotion from framer-motion (use \`useMediaQuery("(prefers-reduced-motion: reduce)")\` from @/hooks/useMediaQuery DEFAULT export instead per W184 SW6 + W190 broader sweep + W191 SW3 ESLint rule):\n  ${violations.join("\n  ")}`
    ).toEqual([])
  })

  it("regex captures both Pattern A (combined) + Pattern B (sole) imports", () => {
    // Self-test for the regex — defensive against future regex maintenance
    // changing the semantics inadvertently.
    const patternA = `import { AnimatePresence, m, useReducedMotion } from "framer-motion"`
    const patternB = `import { useReducedMotion } from "framer-motion"`
    const patternBSingle = `import { useReducedMotion } from 'framer-motion'`
    const patternAReversed = `import { useReducedMotion, m, AnimatePresence } from "framer-motion"`

    // Negative cases (must NOT match)
    const reactImport = `import { useReducedMotion } from "react"` // wrong source
    const aliasImport = `import { useReducedMotionAlias } from "framer-motion"` // word-boundary
    const commentOnly = `// useReducedMotion is jsdom-incompatible per W184 SW6`
    const usageNotImport = `const x = useReducedMotion()` // not an import statement

    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(patternA)).toBe(true)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(patternB)).toBe(true)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(patternBSingle)).toBe(true)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(patternAReversed)).toBe(true)

    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(reactImport)).toBe(false)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(aliasImport)).toBe(false)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(commentOnly)).toBe(false)
    expect(FRAMER_MOTION_USE_REDUCED_MOTION_RE.test(usageNotImport)).toBe(false)
  })
})
