// @vitest-environment node

import { expect, it } from "vitest"
import { createQueryClient, setQueryCacheIdentity } from "../queryClient"

it("keeps request-local server caches outside browser identity retirement", () => {
  setQueryCacheIdentity(null)
  const firstRequest = createQueryClient()
  const secondRequest = createQueryClient()
  firstRequest.setQueryData(["schedule"], ["first request schedule"])
  secondRequest.setQueryData(["schedule"], ["second request schedule"])

  try {
    // The router creates one QueryClient per SSR request. Browser cache
    // ownership must not turn those independent clients into shared state.
    setQueryCacheIdentity("A")
    setQueryCacheIdentity("B")
    expect(firstRequest.getQueryData(["schedule"])).toEqual(["first request schedule"])
    expect(secondRequest.getQueryData(["schedule"])).toEqual(["second request schedule"])
  } finally {
    setQueryCacheIdentity(null)
    firstRequest.clear()
    secondRequest.clear()
  }
})
