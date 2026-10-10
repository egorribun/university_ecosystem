import { act } from "@testing-library/react"
import type { AnyRouter } from "@tanstack/react-router"
import { expect } from "vitest"

/**
 * Assert no navigation after a synchronous interaction on static fixture routes.
 * Deferred loaders are unsupported: cleanup reports a pending route immediately.
 */
export async function expectNoRouterNavigation(
  router: AnyRouter,
  interact: () => void
): Promise<void> {
  const historyLocation = router.history.location
  const historyLength = router.history.length
  const navigations: string[] = []
  const unsubscribeStart = router.subscribe("onBeforeNavigate", ({ toLocation }) => {
    navigations.push(toLocation.href)
  })

  try {
    await act(async () => {
      interact()
    })
    expect(navigations, "same-target clicks must not start a route load").toEqual([])
    expect(router.history.location).toEqual(historyLocation)
    expect(router.history.length).toBe(historyLength)
  } finally {
    try {
      // Flush static-route React work even when the no-navigation assertion fails.
      // Read public state instead of awaiting an onResolved event that an aborted
      // or superseded navigation may never emit.
      await act(async () => {})
      expect(
        { status: router.state.status, isLoading: router.state.isLoading },
        "static fixture navigation must settle during the act flush"
      ).toEqual({ status: "idle", isLoading: false })
    } finally {
      unsubscribeStart()
    }
  }
}
