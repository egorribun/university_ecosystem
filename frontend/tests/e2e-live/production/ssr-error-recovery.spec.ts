import { spawn, type ChildProcess } from "node:child_process"
import { copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { createServer } from "node:net"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import type { Page, Response } from "@playwright/test"

import { expect, test as base } from "../../e2e/test"

type FailureServer = {
  origin: string
  attempts: () => Promise<number>
  release: () => Promise<void>
  close: () => Promise<void>
}

type Language = "ru" | "en"

const labels = {
  ru: {
    title: "Что-то пошло не так",
    description: "Не удалось загрузить страницу. Попробуйте снова.",
    retry: "Попробовать снова",
  },
  en: {
    title: "Something went wrong",
    description: "We could not load this page. Please try again.",
    retry: "Try again",
  },
} as const
const privateQuery = "R67_PRIVATE_QUERY_DO_NOT_REFLECT"
const forbiddenDetails = [
  "R67_SYNTHETIC_PRIVATE_RENDER_ERROR",
  "fixtureRenderer",
  "/private/r67-renderer.ts",
  "__r67_error__",
  privateQuery,
]

async function reservePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const reservation = createServer()
    reservation.once("error", reject)
    reservation.listen({ host: "127.0.0.1", port: 0, exclusive: true }, () => {
      const address = reservation.address()
      reservation.close((error) => {
        if (error) reject(error)
        else if (!address || typeof address === "string") reject(new Error("No loopback port"))
        else resolve(address.port)
      })
    })
  })
}

async function waitForListener(child: ChildProcess, port: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    let stdout = ""
    const cleanup = () => {
      clearTimeout(timer)
      child.stdout?.off("data", onData)
      child.off("exit", onExit)
      child.off("error", onError)
    }
    const onData = (chunk: Buffer) => {
      stdout += chunk.toString()
      if (stdout.includes(`server-prod: listening on http://127.0.0.1:${port}`)) {
        cleanup()
        resolve()
      }
    }
    const onExit = (code: number | null, signal: NodeJS.Signals | null) => {
      cleanup()
      reject(new Error(`Synthetic SSR server exited before listening (${code}, ${signal})`))
    }
    const onError = (error: Error) => {
      cleanup()
      reject(error)
    }
    const timer = setTimeout(() => {
      cleanup()
      reject(new Error("Synthetic SSR server did not start within 15 seconds"))
    }, 15_000)
    child.stdout?.on("data", onData)
    child.once("exit", onExit)
    child.once("error", onError)
  })
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => child.kill("SIGKILL"), 2_000)
    child.once("exit", () => {
      clearTimeout(timer)
      resolve()
    })
    child.kill("SIGTERM")
  })
}

async function startFailureServer(): Promise<FailureServer> {
  const root = await mkdtemp(path.join(os.tmpdir(), "ue-r67-ssr-"))
  let child: ChildProcess | undefined
  try {
    const serverDir = path.join(root, "dist", "server")
    await mkdir(serverDir, { recursive: true })
    await writeFile(path.join(root, "package.json"), '{"type":"module"}\n')
    await copyFile(
      fileURLToPath(new URL("./fixtures/r67-renderer.mjs", import.meta.url)),
      path.join(serverDir, "server.js")
    )
    const port = await reservePort()
    child = spawn(
      process.execPath,
      [fileURLToPath(new URL("../../../scripts/server-prod.mjs", import.meta.url))],
      {
        cwd: root,
        env: {
          PATH: process.env.PATH ?? "",
          SYSTEMROOT: process.env.SYSTEMROOT ?? "",
          WINDIR: process.env.WINDIR ?? "",
          TEMP: process.env.TEMP ?? os.tmpdir(),
          TMP: process.env.TMP ?? os.tmpdir(),
          NODE_ENV: "production",
          HOST: "127.0.0.1",
          PORT: String(port),
        },
        stdio: ["ignore", "pipe", "ignore"],
      }
    )
    await waitForListener(child, port)
    const origin = `http://127.0.0.1:${port}`
    const processToStop = child
    const release = async () => {
      const response = await fetch(`${origin}/__r67_release__`, {
        method: "POST",
        signal: AbortSignal.timeout(2_000),
      })
      expect(response.status).toBe(204)
    }
    return {
      origin,
      attempts: async () => {
        const response = await fetch(`${origin}/__r67_attempts__`, {
          signal: AbortSignal.timeout(2_000),
        })
        expect(response.status).toBe(200)
        return Number(await response.text())
      },
      release,
      close: async () => {
        try {
          await release().catch(() => undefined)
          await stopChild(processToStop)
        } finally {
          await rm(root, { recursive: true, force: true })
        }
      },
    }
  } catch (error) {
    if (child) await stopChild(child)
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

const test = base.extend<{ failureServer: FailureServer }>({
  failureServer: async ({ context }, runFixture) => {
    const server = await startFailureServer()
    try {
      await context.clearCookies()
      await runFixture(server)
    } finally {
      await server.close()
    }
  },
})

function nonceFromPolicy(policy: string | undefined): string {
  const scriptSrc = policy
    ?.split(";")
    .find((directive) => directive.trim().startsWith("script-src "))
  const nonce = scriptSrc?.match(/'nonce-([^']+)'/u)?.[1]
  if (!nonce) throw new Error("The failure document has no CSP script nonce")
  return nonce
}

async function assertFailure(
  page: Page,
  response: Response | null,
  language: Language
): Promise<string> {
  expect(response).not.toBeNull()
  if (!response) throw new Error("The browser did not receive a document response")
  expect(response.status()).toBe(500)
  const headers = response.headers()
  expect(headers["content-type"]).toBe("text/html; charset=utf-8")
  expect(headers["cache-control"]).toBe("no-store, private, max-age=0")
  expect(headers["referrer-policy"]).toBe("no-referrer")
  expect(headers["x-content-type-options"]).toBe("nosniff")
  const nonce = nonceFromPolicy(headers["content-security-policy"])
  expect(nonceFromPolicy(headers["content-security-policy-report-only"])).toBe(nonce)
  const html = await response.text()
  expect(html).toContain(`<script nonce="${nonce}">`)
  expect(await page.locator("script").evaluate((script: HTMLScriptElement) => script.nonce)).toBe(
    nonce
  )
  for (const detail of forbiddenDetails) {
    expect(html).not.toContain(detail)
    expect(Object.values(headers).join("\n")).not.toContain(detail)
  }

  await expect(page.locator("html")).toHaveAttribute("lang", language)
  await expect(page).toHaveTitle(labels[language].title)
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(labels[language].title)
  await expect(page.getByText(labels[language].description, { exact: true })).toBeVisible()
  const retry = page.getByRole("button", { name: labels[language].retry, exact: true })
  await expect(retry).toBeVisible()
  await page.keyboard.press("Tab")
  await expect(retry).toBeFocused()
  const geometry = await retry.evaluate((button) => {
    const rect = button.getBoundingClientRect()
    const style = getComputedStyle(button)
    return {
      width: rect.width,
      height: rect.height,
      right: rect.right,
      viewportWidth: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
    }
  })
  expect(geometry.width).toBeGreaterThanOrEqual(44)
  expect(geometry.height).toBeGreaterThanOrEqual(44)
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth)
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth)
  expect(geometry.outlineStyle).not.toBe("none")
  expect(parseFloat(geometry.outlineWidth)).toBeGreaterThan(0)
  return nonce
}

test.describe("Production wrapper SSR error recovery", () => {
  test.use({ serviceWorkers: "block", colorScheme: "light" })

  for (const viewport of [
    { name: "desktop", width: 1280, height: 720 },
    { name: "mobile", width: 390, height: 844 },
  ] as const) {
    test.describe(viewport.name, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height } })
      for (const language of ["ru", "en"] as const) {
        test(`a repeated ${language} failure retries to a recovered document`, async ({
          page,
          context,
          failureServer,
        }) => {
          await context.addCookies([
            { name: "ue:language", value: language, url: failureServer.origin },
          ])
          const target = `${failureServer.origin}/__r67_error__?private=${privateQuery}`
          const navigations: string[] = []
          page.on("request", (request) => {
            if (request.isNavigationRequest() && request.url() === target)
              navigations.push(request.url())
          })

          const first = await page.goto(target)
          const firstNonce = await assertFailure(page, first, language)
          const [second] = await Promise.all([
            page.waitForResponse(
              (response) => response.url() === target && response.request().isNavigationRequest()
            ),
            page.keyboard.press("Enter"),
          ])
          const secondNonce = await assertFailure(page, second, language)
          expect(secondNonce).not.toBe(firstNonce)

          const retry = page.getByRole("button", { name: labels[language].retry, exact: true })
          await retry.evaluate((element) => {
            if (!(element instanceof HTMLButtonElement)) throw new Error("Retry is not a button")
            element.addEventListener("click", () => {
              const previous = Number(sessionStorage.getItem("r67-click-count") ?? 0)
              sessionStorage.setItem("r67-click-count", String(previous + 1))
              sessionStorage.setItem("r67-click-disabled", String(element.disabled))
            })
          })
          const box = await retry.boundingBox()
          if (!box) throw new Error("The retry button has no visible hit target")
          const recoveredResponse = page.waitForResponse(
            (response) => response.url() === target && response.request().isNavigationRequest()
          )
          await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2)
          await expect.poll(() => navigations.length).toBe(3)
          await expect.poll(failureServer.attempts).toBe(3)
          await failureServer.release()
          expect((await recoveredResponse).status()).toBe(200)
          await expect(page.getByRole("heading", { name: "Recovered document" })).toBeVisible()
          expect(page.url()).toBe(target)
          expect(navigations).toHaveLength(3)
          expect(await failureServer.attempts()).toBe(3)
          expect(await page.evaluate(() => sessionStorage.getItem("r67-click-count"))).toBe("1")
          expect(await page.evaluate(() => sessionStorage.getItem("r67-click-disabled"))).toBe(
            "true"
          )
        })
      }
    })
  }

  test("navigation away wins over a pending retry", async ({ page, context, failureServer }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await context.addCookies([{ name: "ue:language", value: "en", url: failureServer.origin }])
    const target = `${failureServer.origin}/__r67_error__?private=${privateQuery}`
    await assertFailure(page, await page.goto(target), "en")
    const [second] = await Promise.all([
      page.waitForResponse(
        (response) => response.url() === target && response.request().isNavigationRequest()
      ),
      page.keyboard.press("Enter"),
    ])
    await assertFailure(page, second, "en")
    const retry = page.getByRole("button", { name: labels.en.retry })
    const box = await retry.boundingBox()
    if (!box) throw new Error("The retry button has no visible hit target")
    const cancelledRetry = page.waitForEvent(
      "requestfailed",
      (request) => request.url() === target && request.isNavigationRequest()
    )
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
    await expect.poll(failureServer.attempts).toBe(3)
    const destination = `${failureServer.origin}/__r67_safe__`
    expect((await page.goto(destination))?.status()).toBe(200)
    expect((await cancelledRetry).failure()?.errorText).toContain("ERR_ABORTED")
    await failureServer.release()
    await expect(page.getByRole("heading", { name: "Safe destination" })).toBeVisible()
    expect(page.url()).toBe(destination)
  })
})
