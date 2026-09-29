/**
 * Regression guard for the matte-minimalism cleanup (MVP spec §3 and §10).
 *
 * The navbar bottom glow, the hover tilt/wobble hook and the footer ambient
 * orbs were removed from the product. Their tokens, hook and backdrop
 * component must not come back as unused or reintroduced source, so this
 * test scans every production source and stylesheet under `frontend/src`.
 */
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"
import { glob } from "glob"
import { describe, expect, it } from "vitest"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const SRC_ROOT = path.resolve(__dirname, "..")

const REMOVED_DECORATIVE_EFFECTS_RE =
  /--nav-glow-(?:line|spread)\b|--footer-orb-\w+|\buseTilt\b|\bdash-tilt-card\b|\bFooterBackdrop\b/

describe("Decorative effect removal", () => {
  it("no production source or stylesheet reintroduces a removed decorative effect", async () => {
    const files = await glob("**/*.{ts,tsx,css}", {
      cwd: SRC_ROOT,
      ignore: [
        "tests/**",
        "**/__tests__/**",
        "**/*.test.{ts,tsx}",
        "**/*.spec.{ts,tsx}",
        "**/*.stories.{ts,tsx}",
      ],
    })
    expect(files.length).toBeGreaterThan(0)

    const violations = files.filter((relFile) =>
      REMOVED_DECORATIVE_EFFECTS_RE.test(readFileSync(path.join(SRC_ROOT, relFile), "utf-8"))
    )

    expect(violations).toEqual([])
  })

  it("matches every removed decorative effect and nothing adjacent", () => {
    for (const sample of [
      "--nav-glow-line: red;",
      "--nav-glow-spread: red;",
      "background: var(--footer-orb-primary);",
      'import { useTilt } from "@/hooks/useTilt"',
      ".dash-tilt-card { color: red }",
      "<FooterBackdrop />",
    ]) {
      expect(REMOVED_DECORATIVE_EFFECTS_RE.test(sample), sample).toBe(true)
    }
    for (const sample of ["--nav-hover-bg: red;", "useTiltedAxis", "--footer-accent-line: red;"]) {
      expect(REMOVED_DECORATIVE_EFFECTS_RE.test(sample), sample).toBe(false)
    }
  })
})
