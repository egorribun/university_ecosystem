import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { resolve } from "node:path"

import { expect, test, type Locator, type Page } from "@playwright/test"
import sharp from "sharp"
import { createServer, type Plugin, type ViteDevServer } from "vite"

// Render the real component with the app's Tailwind and messenger styles. A
// virtual entry keeps the fixture out of the application and avoids a build.
const entry = `
  import React from "react"
  import { createRoot } from "react-dom/client"
  import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
  import { LazyMotion, MotionConfig, domAnimation } from "framer-motion"
  import { I18nextProvider } from "react-i18next"
  import { createI18nInstance } from "/src/i18n/config.ts"
  import { ChatWindow } from "/src/components/messenger/ChatWindow.tsx"
  import "/src/styles/tailwind.css"
  import "/src/styles/tokens/messenger.css"

  const messages = [{
    id: "contrast-reply", senderId: "me", senderName: "Me", timestamp: "12:34",
    text: "Sent body for contrast", isMe: true, status: "read", editedAt: "2026-01-01",
    attachments: [{ id: "file", type: "file", url: "/example.pdf", name: "Contrast file.pdf", size: 2048 }],
    replyTo: { id: "reply", isMe: false, senderName: "Quoted author", text: "Quoted reply text", deletedAt: null },
  }, {
    id: "contrast-forward", senderId: "me", senderName: "Me", timestamp: "12:35",
    text: "Forwarded body for contrast", isMe: true, forwardedFromName: "Forwarded author",
  }]
  const h = React.createElement
  createRoot(document.getElementById("root")).render(
    h(I18nextProvider, { i18n: createI18nInstance("en") },
      h(QueryClientProvider, { client: new QueryClient() },
        h(LazyMotion, { features: domAnimation },
          h(MotionConfig, { reducedMotion: "never" },
            h("div", { className: "messenger-theme flex flex-col bg-msg-chat text-text-primary", style: { height: 700, width: "100%", maxWidth: 800 } },
              h(ChatWindow, { messages, onStartReply: () => {}, onForward: () => {} })
            )
          )
        )
      )
    )
  )
`

const fixturePlugin = (): Plugin => ({
  name: "sent-bubble-contrast-fixture",
  resolveId(id) {
    if (id === "virtual:sent-bubble-contrast") return "\0sent-bubble-contrast"
  },
  load(id) {
    if (id === "\0sent-bubble-contrast") return entry
  },
  configureServer(server) {
    server.middlewares.use("/contrast-fixture", (_request, response) => {
      response.setHeader("Content-Type", "text/html")
      response.end(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body><div id="root"></div>' +
          '<script type="module" src="/@id/virtual:sent-bubble-contrast"></script></body></html>'
      )
    })
  },
})

const linear = (value: number) => {
  const channel = value / 255
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
}

const luminance = ([r, g, b]: number[]) =>
  0.2126 * linear(r!) + 0.7152 * linear(g!) + 0.0722 * linear(b!)

const contrast = (left: number[], right: number[]) => {
  const [lighter, darker] = [luminance(left), luminance(right)].sort((a, b) => b - a)
  return (lighter! + 0.05) / (darker! + 0.05)
}

type Sample = {
  name: string
  locator: Locator
  box: { x: number; y: number; width: number; height: number }
  color: string
  opacity: number
}

async function sampleText(name: string, locator: Locator): Promise<Sample> {
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  if (!box) throw new Error(`Missing bounds for ${name}`)
  const { color, opacity } = await locator.evaluate((element) => {
    const computed = getComputedStyle(element)
    let opacity = 1
    for (let node: Element | null = element; node; node = node.parentElement) {
      opacity *= Number(getComputedStyle(node).opacity)
    }
    return { color: computed.color, opacity }
  })
  return { name, locator, box, color, opacity }
}

async function renderedContrast(page: Page, samples: Sample[]) {
  // Hide the glyphs without hiding their backgrounds, then sample all rendered
  // background pixels under each text box. This includes the browser's actual
  // gradient interpolation, white reply/attachment overlays and hover state.
  const cover = await page.addStyleTag({
    content:
      "* { color: transparent !important; text-shadow: none !important; caret-color: transparent !important } " +
      "svg, img { visibility: hidden !important } " +
      "[data-aud073-text]::after { content: ''; position: absolute; inset: 0; " +
      "background: var(--aud073-color); z-index: 2147483647; pointer-events: none }",
  })
  const backgroundImage = await page.screenshot({ animations: "disabled" })
  // Cover each text box with its computed color and take a second screenshot.
  // The browser itself composites text alpha and ancestor opacity, avoiding
  // assumptions about nested transparency or gradient color interpolation.
  for (const sample of samples) {
    await sample.locator.evaluate((element, color) => {
      const html = element as HTMLElement
      html.dataset.aud073Text = ""
      html.style.setProperty("--aud073-color", color)
      html.style.setProperty("position", "relative", "important")
    }, sample.color)
  }
  const foregroundImage = await page.screenshot({ animations: "disabled" })
  for (const sample of samples) {
    await sample.locator.evaluate((element) => {
      const html = element as HTMLElement
      delete html.dataset.aud073Text
      html.style.removeProperty("--aud073-color")
      html.style.removeProperty("position")
    })
  }
  await cover.evaluate((element) => {
    element.parentNode?.removeChild(element)
  })
  const { data: backgrounds, info } = await sharp(backgroundImage)
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true })
  const foregrounds = await sharp(foregroundImage).removeAlpha().raw().toBuffer()
  const viewport = page.viewportSize()
  if (!viewport) throw new Error("A fixed viewport is required")
  const scale = info.width / viewport.width

  const results = []
  for (const sample of samples) {
    const { x, y, width, height } = sample.box
    expect(x, `${sample.name}: left edge`).toBeGreaterThanOrEqual(0)
    expect(y, `${sample.name}: top edge`).toBeGreaterThanOrEqual(0)
    expect(x + width, `${sample.name}: right edge`).toBeLessThanOrEqual(viewport.width)
    expect(y + height, `${sample.name}: bottom edge`).toBeLessThanOrEqual(viewport.height)
    const left = Math.max(0, Math.ceil(x * scale))
    const top = Math.max(0, Math.ceil(y * scale))
    const right = Math.min(info.width, Math.floor((x + width) * scale))
    const bottom = Math.min(info.height, Math.floor((y + height) * scale))
    expect(right - left, sample.name).toBeGreaterThan(0)
    expect(bottom - top, sample.name).toBeGreaterThan(0)
    let minimum = Number.POSITIVE_INFINITY
    let worstBackground: number[] = []
    let worstForeground: number[] = []
    for (let row = top; row < bottom; row++) {
      for (let column = left; column < right; column++) {
        const index = (row * info.width + column) * info.channels
        const background = [backgrounds[index]!, backgrounds[index + 1]!, backgrounds[index + 2]!]
        const foreground = [foregrounds[index]!, foregrounds[index + 1]!, foregrounds[index + 2]!]
        const value = contrast(foreground, background)
        if (value < minimum) {
          minimum = value
          worstBackground = background
          worstForeground = foreground
        }
      }
    }
    results.push({
      name: sample.name,
      color: sample.color,
      opacity: sample.opacity,
      background: worstBackground,
      foreground: worstForeground,
      minimum,
    })
  }
  return results
}

let server: ViteDevServer
let cacheDir: string
let baseUrl: string

test.beforeAll(async () => {
  cacheDir = await mkdtemp(resolve(tmpdir(), "aud073-vite-"))
  server = await createServer({
    root: process.cwd(),
    configFile: false,
    cacheDir,
    appType: "custom",
    resolve: { alias: { "@": resolve(process.cwd(), "src") } },
    plugins: [fixturePlugin()],
    optimizeDeps: {
      noDiscovery: true,
      include: [
        "react",
        "react/jsx-dev-runtime",
        "react/jsx-runtime",
        "react-dom/client",
        "@tanstack/react-query",
        "@tanstack/react-virtual",
        "framer-motion",
        "react-i18next",
        "i18next",
        "lucide-react",
        "@floating-ui/react",
        "clsx",
        "tailwind-merge",
      ],
    },
    server: { host: "127.0.0.1", port: 0, strictPort: true, watch: { ignored: ["**/*"] } },
  })
  await server.listen()
  const address = server.httpServer?.address()
  if (!address || typeof address === "string") throw new Error("Vite did not bind a TCP port")
  baseUrl = `http://127.0.0.1:${address.port}`
})

test.afterAll(async () => {
  await server?.close()
  if (cacheDir) await rm(cacheDir, { recursive: true, force: true })
})

const scenarios = [
  { name: "light desktop", theme: "light", width: 1000 },
  { name: "dark desktop", theme: "dark", width: 1000 },
  { name: "light mobile", theme: "light", width: 360 },
  { name: "dark mobile", theme: "dark", width: 360 },
] as const

for (const { name, theme, width } of scenarios) {
  test(`sent messages have AA text contrast on ${name}`, async ({ page }) => {
    const pageErrors: string[] = []
    page.on("pageerror", (error) => {
      pageErrors.push(error.message)
      console.error("Fixture page error:", error.message)
    })
    page.on("console", (message) => {
      if (message.type() === "error") console.error("Fixture console error:", message.text())
    })
    await page.setViewportSize({ width, height: 800 })
    await page.emulateMedia({ reducedMotion: "no-preference" })
    await page.goto(`${baseUrl}/contrast-fixture`)
    if (theme === "dark") {
      await page.evaluate(() => document.documentElement.classList.add("dark"))
    }
    await page.addStyleTag({ content: "*, *::before, *::after { transition: none !important }" })
    const replyBubble = page.getByText("Sent body for contrast").locator("..")
    const forwardBubble = page.getByText("Forwarded body for contrast").locator("..")
    const samples = await Promise.all([
      sampleText("message body", replyBubble.getByText("Sent body for contrast")),
      sampleText("quoted author", replyBubble.getByText("Quoted author")),
      sampleText("quoted reply", replyBubble.getByText("Quoted reply text")),
      sampleText("attachment name", replyBubble.getByText("Contrast file.pdf")),
      sampleText("attachment size", replyBubble.getByText("2.0 KB")),
      sampleText("edited label", replyBubble.getByText("(edited)")),
      sampleText("timestamp", replyBubble.getByText("12:34")),
      sampleText("forwarded header", forwardBubble.getByText(/Forwarded author/)),
      sampleText("forwarded body", forwardBubble.getByText("Forwarded body for contrast")),
    ])
    const normal = await renderedContrast(page, samples)

    const hovered: Awaited<ReturnType<typeof renderedContrast>> = []
    if (await page.evaluate(() => matchMedia("(hover: hover)").matches)) {
      const attachment = replyBubble.getByRole("link", { name: /Contrast file.pdf/ })
      const beforeHover = await attachment.evaluate(
        (element) => getComputedStyle(element).backgroundColor
      )
      await attachment.hover()
      await expect
        .poll(() => attachment.evaluate((element) => getComputedStyle(element).backgroundColor))
        .not.toBe(beforeHover)
      hovered.push(
        ...(await renderedContrast(page, [
          await sampleText("hovered attachment name", replyBubble.getByText("Contrast file.pdf")),
          await sampleText("hovered attachment size", replyBubble.getByText("2.0 KB")),
        ]))
      )
    }
    await test.info().attach(`contrast-${name}`, {
      body: JSON.stringify([...normal, ...hovered]),
      contentType: "application/json",
    })
    for (const result of [...normal, ...hovered]) {
      expect(result.minimum, `${result.name}: minimum rendered contrast`).toBeGreaterThanOrEqual(
        4.5
      )
    }
    expect(pageErrors).toEqual([])
  })
}

test("detects the original low-contrast violet gradient", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 })
  await page.emulateMedia({ reducedMotion: "no-preference" })
  await page.goto(`${baseUrl}/contrast-fixture`)
  const message = page.getByText("Sent body for contrast")
  await expect(message).toBeVisible()
  // Historical stops from the original AUD-073 finding. Override only this
  // fixture to prove that the browser contrast measurement catches regression.
  await page.locator(".messenger-theme").evaluate((element) => {
    ;(element as HTMLElement).style.setProperty(
      "--messenger-bubble-sent-bg",
      "linear-gradient(135deg, var(--color-violet-500) 0%, var(--color-violet-400) 100%)"
    )
  })
  const [result] = await renderedContrast(page, [await sampleText("original gradient", message)])
  if (!result) throw new Error("Missing original gradient sample")
  await test.info().attach("contrast-historical", {
    body: JSON.stringify(result),
    contentType: "application/json",
  })
  expect(result.minimum).toBeLessThan(4.5)
})

test("detects a translucent sent text regression", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 })
  await page.emulateMedia({ reducedMotion: "no-preference" })
  await page.goto(`${baseUrl}/contrast-fixture`)
  const message = page.getByText("Sent body for contrast")
  await expect(message).toBeVisible()
  await message.evaluate((element) => {
    ;(element as HTMLElement).style.opacity = "0.5"
  })
  const [result] = await renderedContrast(page, [await sampleText("translucent text", message)])
  if (!result) throw new Error("Missing translucent text sample")
  await test.info().attach("contrast-alpha", {
    body: JSON.stringify(result),
    contentType: "application/json",
  })
  expect(result.opacity).toBe(0.5)
  expect(result.minimum).toBeLessThan(4.5)
})
