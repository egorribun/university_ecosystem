import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

import {
  initializeSmokeTheme,
  isThemeVariantProbeRoute,
  systemSchemeForRoute,
  THEME_VARIANT_ROUTE,
  THEME_VARIANT_SELECTOR,
  verifyThemeVariant,
} from "./unauthenticated-routes-theme.mjs"

const DARK_BACKGROUND = "color(srgb 1 1 1 / 0.08)"
const LIGHT_BACKGROUND = "color(srgb 0 0 0 / 0.08)"

async function withGlobals(values, callback) {
  const previous = new Map()
  for (const [name, value] of Object.entries(values)) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      writable: true,
      value,
    })
  }
  try {
    return await callback()
  } finally {
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
}

function fakePage({
  route = THEME_VARIANT_ROUTE,
  darkClass = true,
  backgroundColor = DARK_BACKGROUND,
  rgba = [255, 255, 255, 20],
  cssSupported = true,
  targetExists = true,
  pollsBeforeSettled = 0,
  canvasParsesColor = true,
} = {}) {
  const calls = []
  const storageWrites = []
  let hovered = false
  let initScript = null
  let assignedCanvasColor = null
  let animationChecks = 0
  const canvasContext = {
    clearRect: () => calls.push(["canvas-clear"]),
    fillRect: () => calls.push(["canvas-fill"]),
    getImageData: () => ({ data: Uint8ClampedArray.from(rgba) }),
    get fillStyle() {
      return assignedCanvasColor
    },
    set fillStyle(value) {
      if (value === "rgba(1, 2, 3, 0)" || canvasParsesColor) {
        assignedCanvasColor = value
      }
      calls.push(["canvas-color", value])
    },
  }
  const documentStub = {
    documentElement: {
      classList: {
        contains: (className) => className === "dark" && darkClass,
      },
    },
    querySelector: (selector) =>
      targetExists && selector === THEME_VARIANT_SELECTOR
        ? {
            matches: (state) => state === ":hover" && hovered,
            getAnimations: () => {
              animationChecks += 1
              return animationChecks <= pollsBeforeSettled ? [{ playState: "running" }] : []
            },
          }
        : null,
    createElement: (tagName) => {
      if (tagName !== "canvas") throw new Error(`Unexpected element: ${tagName}`)
      return {
        width: 0,
        height: 0,
        getContext: (kind) => (kind === "2d" ? canvasContext : null),
      }
    },
  }

  const page = {
    calls,
    storageWrites,
    context: () => ({
      addCookies: async (cookies) => calls.push(["cookies", cookies]),
    }),
    addInitScript: async (script, argument) => {
      initScript = { script, argument }
      calls.push(["init-script", argument])
    },
    emulateMedia: async (options) => calls.push(["emulate-media", options]),
    url: () => `http://localhost${route}`,
    locator: (selector) => ({
      waitFor: async (options) => calls.push(["wait-for", selector, options]),
      hover: async () => {
        hovered = true
        calls.push(["hover", selector])
      },
    }),
    waitForFunction: async (callback, argument, options) => {
      calls.push(["wait-for-function", options])
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const result = await withGlobals(
          {
            document: documentStub,
            getComputedStyle: () => ({ backgroundColor }),
            CSS: { supports: (_property, _value) => cssSupported },
          },
          () => callback(argument)
        )
        if (result) return { jsonValue: async () => result }
      }
      throw new Error(`Timeout ${options.timeout}ms exceeded`)
    },
    evaluate: async (callback, argument) => {
      calls.push(["evaluate", callback.name || "anonymous"])
      return withGlobals(
        {
          document: documentStub,
          getComputedStyle: () => ({ backgroundColor }),
          CSS: { supports: (_property, _value) => cssSupported },
        },
        () => callback(argument)
      )
    },
    runInitScript: async () => {
      if (!initScript) throw new Error("init script was not registered")
      await withGlobals(
        {
          localStorage: {
            setItem: (key, value) => storageWrites.push([key, value]),
          },
        },
        () => initScript.script(initScript.argument)
      )
    },
    assignedCanvasColor: () => assignedCanvasColor,
  }
  return page
}

test("only the target route opposes OS preference while cookie and localStorage keep explicit theme", async () => {
  assert.equal(isThemeVariantProbeRoute("/reset-password"), true)
  assert.equal(isThemeVariantProbeRoute("/login"), false)

  for (const theme of ["light", "dark"]) {
    const probePage = fakePage()
    const probeSettings = await initializeSmokeTheme(probePage, {
      origin: "http://localhost",
      routePath: THEME_VARIANT_ROUTE,
      theme,
    })
    await probePage.runInitScript()
    assert.deepEqual(probePage.calls.find(([kind]) => kind === "cookies")[1], [
      { name: "ue-mode", value: theme, domain: "localhost", path: "/" },
    ])
    assert.deepEqual(probePage.storageWrites, [["ue-mode", theme]])
    assert.deepEqual(probePage.calls.find(([kind]) => kind === "emulate-media")[1], {
      colorScheme: theme === "dark" ? "light" : "dark",
    })
    assert.deepEqual(probeSettings, {
      explicitTheme: theme,
      systemColorScheme: theme === "dark" ? "light" : "dark",
    })

    const ordinaryPage = fakePage()
    const ordinarySettings = await initializeSmokeTheme(ordinaryPage, {
      origin: "http://localhost",
      routePath: "/login",
      theme,
    })
    assert.deepEqual(ordinaryPage.calls.find(([kind]) => kind === "emulate-media")[1], {
      colorScheme: theme,
    })
    assert.deepEqual(ordinarySettings, {
      explicitTheme: theme,
      systemColorScheme: theme,
    })
    assert.equal(systemSchemeForRoute("/login", theme), theme)
  }
})

test("dark utility probe accepts a white computed hover color for explicit dark under light OS", async () => {
  const page = fakePage({
    backgroundColor: DARK_BACKGROUND,
    rgba: [255, 255, 255, 20],
    pollsBeforeSettled: 2,
  })
  const result = await verifyThemeVariant(page, "dark")
  assert.deepEqual(result, {
    passed: true,
    explicitTheme: "dark",
    systemColorScheme: "light",
    documentDarkClass: true,
    selector: THEME_VARIANT_SELECTOR,
    backgroundColor: DARK_BACKGROUND,
    backgroundAlpha: 20 / 255,
    backgroundLuminance: 1,
  })
  assert.equal(page.assignedCanvasColor(), DARK_BACKGROUND)
  const hoverIndex = page.calls.findIndex(([kind]) => kind === "hover")
  const waitIndex = page.calls.findIndex(([kind]) => kind === "wait-for-function")
  const colorSampleIndex = page.calls.findIndex(([kind]) => kind === "canvas-color")
  assert.ok(hoverIndex >= 0 && hoverIndex < waitIndex && waitIndex < colorSampleIndex)
  assert.deepEqual(page.calls[waitIndex][1], { timeout: 5_000, polling: 50 })
  assert.deepEqual(
    page.calls.filter(([kind]) => kind === "canvas-color").map(([, color]) => color),
    ["rgba(1, 2, 3, 0)", DARK_BACKGROUND]
  )
})

test("dark utility probe accepts a black computed hover color for explicit light under dark OS", async () => {
  const page = fakePage({
    darkClass: false,
    backgroundColor: LIGHT_BACKGROUND,
    rgba: [0, 0, 0, 20],
  })
  const result = await verifyThemeVariant(page, "light")
  assert.equal(result.passed, true)
  assert.equal(result.systemColorScheme, "dark")
  assert.equal(result.documentDarkClass, false)
  assert.equal(result.backgroundLuminance, 0)
  assert.equal(result.backgroundAlpha, 20 / 255)
  assert.equal(page.assignedCanvasColor(), LIGHT_BACKGROUND)
})

test("dark utility probe rejects a root theme class that follows the system instead", async () => {
  const darkUnderLightSystem = fakePage({ darkClass: false })
  await assert.rejects(verifyThemeVariant(darkUnderLightSystem, "dark"), /document \.dark=true/)

  const lightUnderDarkSystem = fakePage({ darkClass: true })
  await assert.rejects(verifyThemeVariant(lightUnderDarkSystem, "light"), /document \.dark=false/)
})

test("dark utility probe rejects the wrong computed luminance and transparent hover colors", async () => {
  await assert.rejects(
    verifyThemeVariant(fakePage({ rgba: [0, 0, 0, 20] }), "dark"),
    /Timed out waiting for the dark utility hover color for explicit dark theme/
  )
  await assert.rejects(
    verifyThemeVariant(
      fakePage({
        darkClass: false,
        backgroundColor: LIGHT_BACKGROUND,
        rgba: [255, 255, 255, 20],
      }),
      "light"
    ),
    /Timed out waiting for the dark utility hover color for explicit light theme/
  )
  await assert.rejects(
    verifyThemeVariant(fakePage({ rgba: [255, 255, 255, 0] }), "dark"),
    /Timed out waiting for the dark utility hover color for explicit dark theme/
  )
})

test("dark utility probe fails closed on wrong route, missing target, or unsupported color", async () => {
  await assert.rejects(
    verifyThemeVariant(fakePage({ route: "/forgot-password" }), "dark"),
    /expected \/reset-password/
  )
  await assert.rejects(
    verifyThemeVariant(fakePage({ targetExists: false }), "dark"),
    /target #reset-password-toggle is missing/
  )
  await assert.rejects(
    verifyThemeVariant(fakePage({ cssSupported: false }), "dark"),
    /unsupported computed color/
  )
  await assert.rejects(
    verifyThemeVariant(fakePage({ canvasParsesColor: false }), "dark"),
    /Timed out waiting for the dark utility hover color for explicit dark theme/
  )
  await assert.rejects(verifyThemeVariant(fakePage(), "sepia"), /Unsupported explicit theme/)
})

test("probe selector binds to the production reset-password dark utility", () => {
  const sourcePath = new URL("../src/pages/ResetPassword.tsx", import.meta.url)
  const source = readFileSync(sourcePath, "utf8")
  const target = source.match(/id="reset-password-toggle"[\s\S]*?className="([^"]+)"/u)
  assert.ok(target, "the production reset-password theme probe control must exist")
  assert.match(target[1], /hover:bg-black\/\[calc\(var\(--opacity-subtle\)\*100%\)\]/u)
  assert.match(target[1], /dark:hover:bg-white\/\[calc\(var\(--opacity-subtle\)\*100%\)\]/u)
})

test("smoke runner invokes the tested theme setup and records a failing style assertion", () => {
  const runnerPath = new URL("./unauthenticated-routes-smoke.mjs", import.meta.url)
  const runner = readFileSync(runnerPath, "utf8")
  assert.match(runner, /await initializeSmokeTheme\(page, \{ origin: ORIGIN, routePath, theme \}\)/)
  assert.match(runner, /if \(isThemeVariantProbeRoute\(routePath\)\)/)
  assert.match(runner, /themeVariantCheck = await verifyThemeVariant\(page, theme\)/)
  assert.match(runner, /themeVariantCheck,\s*themeVariantError/)
  assert.match(runner, /s\.themeVariantError/)
})
