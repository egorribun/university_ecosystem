// @vitest-environment node

import { renderToString } from "react-dom/server"
import { afterEach, expect, it, vi } from "vitest"

const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage")

afterEach(() => {
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage)
  else Reflect.deleteProperty(globalThis, "localStorage")
  vi.restoreAllMocks()
})

it("imports and server-renders the system fallback without reading server storage or emitting storage warnings", async () => {
  expect(typeof window).toBe("undefined")
  // Vitest's isolated Node global omits the host's native storage accessor.
  // Install a throwing getter to enforce the same browser boundary directly.
  const storageGetter = vi.fn(() => {
    throw new Error("server storage is unavailable")
  })
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get: storageGetter,
  })
  const warnings: Error[] = []
  const onWarning = (warning: Error) => warnings.push(warning)
  process.on("warning", onWarning)
  try {
    const { ThemeProvider, useTheme } = await import("../ThemeContext")
    expect(storageGetter).not.toHaveBeenCalled()
    function Consumer() {
      const { theme, resolvedTheme } = useTheme()
      return <output>{`${theme}/${resolvedTheme}`}</output>
    }
    expect(
      renderToString(
        <ThemeProvider>
          <Consumer />
        </ThemeProvider>
      )
    ).toBe("<output>system/light</output>")
    await new Promise<void>((resolve) => setImmediate(resolve))
    expect(storageGetter).not.toHaveBeenCalled()
    expect(warnings).toEqual([])
  } finally {
    process.removeListener("warning", onWarning)
  }
})

it("does not consume a server process's available persistent theme during SSR", async () => {
  const getItem = vi.fn(() => "dark")
  const storageGetter = vi.fn(() => ({ getItem }))
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get: storageGetter,
  })
  const { ThemeProvider, useTheme } = await import("../ThemeContext")
  function Consumer() {
    return <output>{useTheme().theme}</output>
  }
  expect(
    renderToString(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>
    )
  ).toBe("<output>system</output>")
  expect(storageGetter).not.toHaveBeenCalled()
  expect(getItem).not.toHaveBeenCalled()
})
