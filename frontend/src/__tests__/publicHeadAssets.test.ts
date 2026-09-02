import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const frontendRoot = process.cwd()
const publicDir = resolve(frontendRoot, "public")

const headIcons = [
  "favicon.ico",
  "favicon-32x32.png",
  "favicon-16x16.png",
  "apple-touch-icon.png",
] as const

describe("public head assets", () => {
  it("ships a valid robots policy instead of falling back to the SPA document", () => {
    const robots = readFileSync(resolve(publicDir, "robots.txt"), "utf8")

    expect(robots).toMatch(/^User-agent:\s*\*/mu)
    expect(robots).toContain("Disallow: /api/")
    expect(robots).not.toMatch(/<html|<!doctype/iu)
  })

  it.each(headIcons)("ships %s referenced by both static and SSR heads", (filename) => {
    const href = `/${filename}`
    const staticShell = readFileSync(resolve(frontendRoot, "index.html"), "utf8")
    const rootRoute = readFileSync(resolve(frontendRoot, "src/routes/__root.tsx"), "utf8")

    expect(staticShell).toContain(`href="${href}"`)
    expect(rootRoute).toContain(`href: "${href}"`)
    expect(existsSync(resolve(publicDir, filename))).toBe(true)
  })

  it.each(["manifest.webmanifest", "manifest.en.webmanifest"])(
    "ships every icon referenced by %s",
    (manifestFilename) => {
      const manifest = JSON.parse(readFileSync(resolve(publicDir, manifestFilename), "utf8")) as {
        icons?: Array<{ src?: string }>
        shortcuts?: Array<{ icons?: Array<{ src?: string }> }>
      }
      const iconSources = [
        ...(manifest.icons ?? []).map((icon) => icon.src),
        ...(manifest.shortcuts ?? []).flatMap((shortcut) =>
          (shortcut.icons ?? []).map((icon) => icon.src)
        ),
      ].filter((source): source is string => Boolean(source))

      expect(iconSources.length).toBeGreaterThan(0)
      for (const source of iconSources) {
        expect(source.startsWith("/")).toBe(true)
        expect(existsSync(resolve(publicDir, source.slice(1)))).toBe(true)
      }
    }
  )
})
