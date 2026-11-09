export const THEME_VARIANT_ROUTE = "/reset-password"
export const THEME_VARIANT_SELECTOR = "#reset-password-toggle"
const THEME_VARIANT_WAIT_TIMEOUT_MS = 5_000
const THEME_VARIANT_POLLING_MS = 50

function requireTheme(theme) {
  if (theme !== "light" && theme !== "dark") {
    throw new TypeError(`Unsupported explicit theme: ${String(theme)}`)
  }
}

export function isThemeVariantProbeRoute(routePath) {
  return routePath === THEME_VARIANT_ROUTE
}

export function systemSchemeForRoute(routePath, theme) {
  requireTheme(theme)
  if (isThemeVariantProbeRoute(routePath)) return theme === "dark" ? "light" : "dark"
  return theme
}

export async function initializeSmokeTheme(page, { origin, routePath, theme }) {
  requireTheme(theme)
  const cookieDomain = new URL(origin).hostname
  await page.context().addCookies([
    {
      name: "ue-mode",
      value: theme,
      domain: cookieDomain,
      path: "/",
    },
  ])
  await page.addInitScript((themeName) => {
    try {
      localStorage.setItem("ue-mode", themeName)
    } catch {
      // ignore Safari private-browsing failures (RZ-31-03)
    }
  }, theme)
  const systemColorScheme = systemSchemeForRoute(routePath, theme)
  await page.emulateMedia({ colorScheme: systemColorScheme })
  return { explicitTheme: theme, systemColorScheme }
}

function timeoutMessage(theme, diagnostic, cause) {
  const expectedDarkClass = theme === "dark"
  if (!diagnostic?.targetExists) {
    return `Theme variant probe target ${THEME_VARIANT_SELECTOR} is missing`
  }
  if (diagnostic.documentDarkClass !== expectedDarkClass) {
    return (
      `Explicit ${theme} theme expected document .dark=${expectedDarkClass}, ` +
      `got ${diagnostic.documentDarkClass}`
    )
  }
  if (!diagnostic.hovered) {
    return `Theme variant probe target ${THEME_VARIANT_SELECTOR} did not remain hovered`
  }
  if (!diagnostic.colorSupported) {
    return `Theme variant probe received an unsupported computed color: ${diagnostic.backgroundColor}`
  }
  const expected = expectedDarkClass ? "light" : "dark"
  return (
    `Timed out waiting for the dark utility hover color for explicit ${theme} theme ` +
    `(expected ${expected} luminance and nonzero alpha); got ${diagnostic.backgroundColor}. ` +
    `${cause instanceof Error ? cause.message : String(cause)}`
  )
}

export async function verifyThemeVariant(page, theme) {
  requireTheme(theme)
  const expectedDarkClass = theme === "dark"
  const currentPath = new URL(page.url()).pathname
  if (currentPath !== THEME_VARIANT_ROUTE) {
    throw new Error(`Theme variant probe expected ${THEME_VARIANT_ROUTE}, received ${currentPath}`)
  }

  const toggle = page.locator(THEME_VARIANT_SELECTOR)
  await toggle.waitFor({
    state: "visible",
    timeout: THEME_VARIANT_WAIT_TIMEOUT_MS,
  })
  await toggle.hover()

  let sampleHandle
  try {
    sampleHandle = await page.waitForFunction(
      ({ selector, expectedDark }) => {
        const documentDarkClass = globalThis.document.documentElement.classList.contains("dark")
        const element = globalThis.document.querySelector(selector)
        if (documentDarkClass !== expectedDark || !element || !element.matches(":hover")) {
          return false
        }
        if (element.getAnimations().some((animation) => animation.playState === "running")) {
          return false
        }

        const backgroundColor = globalThis.getComputedStyle(element).backgroundColor
        if (!globalThis.CSS.supports("color", backgroundColor)) return false
        const canvas = globalThis.document.createElement("canvas")
        canvas.width = 1
        canvas.height = 1
        const context = canvas.getContext("2d", { willReadFrequently: true })
        if (!context) return false

        context.clearRect(0, 0, 1, 1)
        context.fillStyle = "rgba(1, 2, 3, 0)"
        const sentinelFillStyle = context.fillStyle
        context.fillStyle = backgroundColor
        if (context.fillStyle === sentinelFillStyle) return false
        context.fillRect(0, 0, 1, 1)
        const pixel = context.getImageData(0, 0, 1, 1).data
        const [red, green, blue, alphaByte] = pixel
        const linearize = (value) => {
          const channel = value / 255
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
        }
        const backgroundLuminance =
          0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)
        const backgroundAlpha = alphaByte / 255
        const expectedLuminance = expectedDark
          ? backgroundLuminance >= 0.8
          : backgroundLuminance <= 0.1
        if (backgroundAlpha <= 0 || !expectedLuminance) return false

        return {
          documentDarkClass,
          backgroundColor,
          rgba: [red, green, blue, alphaByte],
          backgroundAlpha,
          backgroundLuminance,
        }
      },
      { selector: THEME_VARIANT_SELECTOR, expectedDark: expectedDarkClass },
      {
        timeout: THEME_VARIANT_WAIT_TIMEOUT_MS,
        polling: THEME_VARIANT_POLLING_MS,
      }
    )
  } catch (cause) {
    const diagnostic = await page.evaluate((selector) => {
      const element = globalThis.document.querySelector(selector)
      const backgroundColor = element ? globalThis.getComputedStyle(element).backgroundColor : null
      return {
        documentDarkClass: globalThis.document.documentElement.classList.contains("dark"),
        targetExists: Boolean(element),
        hovered: Boolean(element?.matches(":hover")),
        backgroundColor,
        colorSupported:
          typeof backgroundColor === "string" && globalThis.CSS.supports("color", backgroundColor),
      }
    }, THEME_VARIANT_SELECTOR)
    throw new Error(timeoutMessage(theme, diagnostic, cause), { cause })
  }

  const sample = await sampleHandle.jsonValue()
  if (!sample || sample.documentDarkClass !== expectedDarkClass) {
    throw new Error(`Explicit ${theme} theme returned an invalid root-class probe result`)
  }
  if (!Array.isArray(sample.rgba) || sample.rgba.length !== 4) {
    throw new Error("Computed background probe did not return RGBA pixels")
  }
  const [red, green, blue, alphaByte] = sample.rgba
  if (![red, green, blue, alphaByte].every(Number.isFinite) || sample.backgroundAlpha <= 0) {
    throw new Error(
      `Hovered dark utility background is transparent or invalid: ${sample.backgroundColor}`
    )
  }
  const backgroundLuminance = sample.backgroundLuminance
  const matchesExplicitTheme = expectedDarkClass
    ? backgroundLuminance >= 0.8
    : backgroundLuminance <= 0.1
  if (!matchesExplicitTheme) {
    const expected = expectedDarkClass ? "light-colored" : "dark-colored"
    throw new Error(
      `Explicit ${theme} theme expected a ${expected} dark-utility hover color, ` +
        `got ${sample.backgroundColor} (luminance=${backgroundLuminance.toFixed(3)})`
    )
  }

  return {
    passed: true,
    explicitTheme: theme,
    systemColorScheme: systemSchemeForRoute(THEME_VARIANT_ROUTE, theme),
    documentDarkClass: sample.documentDarkClass,
    selector: THEME_VARIANT_SELECTOR,
    backgroundColor: sample.backgroundColor,
    backgroundAlpha: sample.backgroundAlpha,
    backgroundLuminance,
  }
}
