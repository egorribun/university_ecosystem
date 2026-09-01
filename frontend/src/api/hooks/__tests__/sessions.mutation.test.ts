import { describe, expect, it, vi } from "vitest"

const apiState = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock("@/api/client", () => ({
  default: apiState,
}))

import { sessionsQueryOptions } from "@/api/hooks/sessions"

describe("sessions query mutation contracts", () => {
  it("forwards the query AbortSignal and returns the active session payload", async () => {
    const sessions = [{ id: "session-1" }]
    apiState.get.mockResolvedValueOnce({ data: sessions })
    const options = sessionsQueryOptions("user-1")
    const signal = new AbortController().signal

    const result = await options.queryFn({
      client: undefined,
      queryKey: options.queryKey,
      signal,
      pageParam: undefined,
      direction: undefined,
      meta: undefined,
    } as never)

    expect(result).toBe(sessions)
    expect(apiState.get).toHaveBeenCalledOnce()
    expect(apiState.get).toHaveBeenCalledWith("/auth/sessions", { signal })
  })
})
