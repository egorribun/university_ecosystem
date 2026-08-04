/**
 * @vitest-environment node
 *
 * Keep the server-only branches of AppShellContext executable in a real
 * Node-like environment. The default jsdom environment always defines
 * `window`, so these guards cannot be exercised there.
 */
import { renderToString } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { AppShellProvider, useAppShell } from "@/contexts/AppShellContext"

const ServerProbe = () => {
  const appShell = useAppShell()

  appShell.scrollToTop()
  appShell.markScrollSnapshot()
  appShell.restoreScrollIfNeeded()

  return null
}

describe("AppShellContext — SSR guards", () => {
  it("keeps browser-only scroll operations inert during server rendering", () => {
    expect(typeof window).toBe("undefined")

    expect(() =>
      renderToString(
        <AppShellProvider>
          <ServerProbe />
        </AppShellProvider>
      )
    ).not.toThrow()
  })
})
