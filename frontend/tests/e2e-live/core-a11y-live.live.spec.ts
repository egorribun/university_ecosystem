import AxeBuilder from "@axe-core/playwright"
import { expect, loginAs, test } from "./fixtures"
import {
  reportLiveA11yPhaseState,
  reportLiveAxeColorContrast,
  reportLiveAxePaintState,
} from "./live-ui-diagnostic"

const CORE_ROUTES = ["/dashboard", "/settings"] as const
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

test.use({ trace: "off", screenshot: "off", video: "off" })

test("real student dashboard and settings have no serious or critical axe findings", async ({
  page,
}, testInfo) => {
  await loginAs(page, "student")

  for (const route of CORE_ROUTES) {
    await page.goto(route)
    await expect(page.getByRole("main")).toBeVisible()
    await expect(page.locator("#main-content")).toBeVisible()
    if (route === "/settings") {
      await expect(page.getByRole("tablist")).toBeVisible()
    }

    const routeName = route === "/dashboard" ? "dashboard" : "settings"
    const reportPageA11yPhase = async (phase: "before_axe" | "after_axe") => {
      try {
        const state = await page.evaluate(() => {
          const root = document.documentElement
          const pageFade = root.querySelector("[data-page-fade]")
          const layout = root.querySelector("[data-scroll-root]")
          const parseOpacity = (element: Element | null) => {
            if (element === null) return 1
            const opacity = Number.parseFloat(window.getComputedStyle(element).opacity)
            return Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1
          }
          const animationProperties = new Set<"opacity" | "transform" | "color">()
          let activeAnimations = 0
          let hasOtherAnimation = false
          let animations: Animation[] = []
          try {
            animations = root.getAnimations({ subtree: true })
          } catch {
            hasOtherAnimation = true
          }
          for (const animation of animations.slice(0, 64)) {
            if (animation.playState !== "running") continue
            activeAnimations += 1
            let classified = false
            try {
              const frames =
                animation.effect instanceof KeyframeEffect ? animation.effect.getKeyframes() : []
              for (const frame of frames) {
                if (frame.opacity !== undefined) {
                  animationProperties.add("opacity")
                  classified = true
                }
                if (frame.transform !== undefined) {
                  animationProperties.add("transform")
                  classified = true
                }
                if (frame.color !== undefined) {
                  animationProperties.add("color")
                  classified = true
                }
              }
            } catch {
              hasOtherAnimation = true
            }
            if (!classified) hasOtherAnimation = true
          }
          if (animations.length > 64) hasOtherAnimation = true
          const animationTag =
            activeAnimations === 0 && !hasOtherAnimation
              ? "none"
              : hasOtherAnimation || animationProperties.size > 1
                ? animationProperties.size === 0
                  ? "other"
                  : "mixed"
                : ([...animationProperties][0] ?? "other")

          return {
            pageFadeReady: pageFade === null || pageFade.getAttribute("data-ready") === "true",
            pageFadeOpacity: parseOpacity(pageFade),
            rootOpacity: parseOpacity(root),
            layoutOpacity: parseOpacity(layout),
            animationTag,
            activeAnimations,
          }
        })
        reportLiveA11yPhaseState(
          testInfo.project.name,
          routeName,
          phase,
          state.pageFadeReady,
          state.pageFadeOpacity,
          state.rootOpacity,
          state.layoutOpacity,
          state.animationTag,
          state.activeAnimations
        )
      } catch {
        // Optional telemetry must never replace the axe assertion.
      }
    }
    await reportPageA11yPhase("before_axe")
    const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
    await reportPageA11yPhase("after_axe")
    const blocking = violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious"
    )

    let reportedContrastNodes = 0
    for (const violation of blocking) {
      if (violation.id !== "color-contrast") continue
      for (const node of violation.nodes) {
        if (reportedContrastNodes >= 4) break
        const contrastCheck = [...node.any, ...node.all, ...node.none].find(
          (check) => check.id === "color-contrast"
        )
        const data: unknown = contrastCheck?.data
        if (typeof data !== "object" || data === null || Array.isArray(data)) continue
        const contrastData = data as {
          fgColor?: unknown
          bgColor?: unknown
          contrastRatio?: unknown
        }

        reportLiveAxeColorContrast(
          testInfo.project.name,
          routeName,
          contrastData.fgColor,
          contrastData.bgColor,
          contrastData.contrastRatio
        )
        // Use axe's target only in memory to inspect paint composition. The
        // diagnostic reporter accepts fixed labels and numeric/color values;
        // no target, selector, node, or text leaves this evaluation.
        try {
          const paint = await page.evaluate((targets) => {
            const element = targets.slice(0, 8).reduce<Element | null>((found, target) => {
              if (found !== null) return found
              if (typeof target !== "string") return null
              try {
                return document.querySelector(target)
              } catch {
                return null
              }
            }, null)
            if (element === null) return null

            const parseOpacity = (current: Element | null) => {
              if (current === null) return 1
              const opacity = Number.parseFloat(window.getComputedStyle(current).opacity)
              return Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1
            }
            const nodeOpacity = parseOpacity(element)
            const color = window.getComputedStyle(element).color
            const colorParts = color.match(/^rgba?\(([^)]{1,128})\)$/iu)
            if (colorParts === null) return null
            const components = colorParts[1]!
              .replaceAll(",", " ")
              .replaceAll("/", " ")
              .trim()
              .split(/\s+/u)
            if (components.length !== 3 && components.length !== 4) return null
            const rawChannels = components.slice(0, 3).map(Number)
            if (rawChannels.some((channel) => !Number.isFinite(channel))) return null
            const channels = rawChannels.map((channel) =>
              Math.max(0, Math.min(255, Math.round(channel)))
            )
            const computedForeground = `#${channels
              .map((channel) => channel.toString(16).padStart(2, "0"))
              .join("")}`
            const alpha = components[3]
            const rawAlpha =
              alpha === undefined
                ? 1
                : alpha.endsWith("%")
                  ? Number(alpha.slice(0, -1)) / 100
                  : Number(alpha)
            if (!Number.isFinite(rawAlpha)) return null
            const foregroundAlpha = Math.max(0, Math.min(1, rawAlpha))

            const ancestors: Element[] = []
            let current: Element | null = element
            while (current !== null && ancestors.length < 32) {
              ancestors.push(current)
              current = current.parentElement
            }
            const ancestorOpacity = ancestors
              .slice(1)
              .reduce((combined, ancestor) => combined * parseOpacity(ancestor), 1)
            const pageFade = element.closest("[data-page-fade]")
            const layout = element.closest("[data-scroll-root]")
            const animationProperties = new Set<"opacity" | "transform" | "color">()
            let activeAnimations = 0
            let hasOtherAnimation = false
            for (const ancestor of ancestors) {
              try {
                for (const animation of ancestor.getAnimations()) {
                  if (animation.playState !== "running") continue
                  activeAnimations += 1
                  let classified = false
                  try {
                    const frames =
                      animation.effect instanceof KeyframeEffect
                        ? animation.effect.getKeyframes()
                        : []
                    for (const frame of frames) {
                      if (frame.opacity !== undefined) {
                        animationProperties.add("opacity")
                        classified = true
                      }
                      if (frame.transform !== undefined) {
                        animationProperties.add("transform")
                        classified = true
                      }
                      if (frame.color !== undefined) {
                        animationProperties.add("color")
                        classified = true
                      }
                    }
                  } catch {
                    hasOtherAnimation = true
                  }
                  if (!classified) hasOtherAnimation = true
                }
              } catch {
                hasOtherAnimation = true
              }
            }
            const animationTag =
              activeAnimations === 0
                ? "none"
                : hasOtherAnimation || animationProperties.size > 1
                  ? animationProperties.size === 0
                    ? "other"
                    : "mixed"
                  : ([...animationProperties][0] ?? "other")
            const textColorTag =
              foregroundAlpha === 0 ? "transparent" : foregroundAlpha < 1 ? "translucent" : "opaque"
            const pageFadeReady =
              pageFade === null || pageFade.getAttribute("data-ready") === "true"
            const opacitySources = [
              nodeOpacity < 0.999,
              ancestorOpacity < 0.999,
              !pageFadeReady || parseOpacity(pageFade) < 0.999,
              parseOpacity(layout) < 0.999,
            ]
            const opacitySourceNames = ["node", "ancestor", "fade", "layout"] as const
            const activeOpacitySources = opacitySources.flatMap((active, index) =>
              active ? [opacitySourceNames[index]] : []
            )
            const opacityTag =
              activeOpacitySources.length === 0
                ? "none"
                : activeOpacitySources.length > 1
                  ? "multiple"
                  : activeOpacitySources[0] === "fade" && !pageFadeReady
                    ? "fade-pending"
                    : activeOpacitySources[0]

            return {
              computedForeground,
              textColorTag,
              opacityTag,
              animationTag,
              foregroundAlpha,
              nodeOpacity: parseOpacity(element),
              ancestorOpacity,
              pageFadeReady,
              pageFadeOpacity: parseOpacity(pageFade),
              layoutOpacity: parseOpacity(layout),
              activeAnimations,
            }
          }, node.target)
          if (paint !== null) {
            reportLiveAxePaintState(
              testInfo.project.name,
              routeName,
              contrastData.fgColor,
              contrastData.bgColor,
              contrastData.contrastRatio,
              paint.computedForeground,
              paint.textColorTag,
              paint.foregroundAlpha,
              paint.nodeOpacity,
              paint.ancestorOpacity,
              paint.opacityTag,
              paint.pageFadeReady,
              paint.pageFadeOpacity,
              paint.layoutOpacity,
              paint.animationTag,
              paint.activeAnimations
            )
          }
        } catch {
          // Optional telemetry must never replace the axe assertion.
        }
        reportedContrastNodes += 1
      }
    }

    // Keep assertion diagnostics to rule identifiers; do not serialize axe nodes.
    expect(
      blocking.map(({ impact, id }) => `${impact}:${id}`),
      `${route} axe rules`
    ).toEqual([])
  }
})
