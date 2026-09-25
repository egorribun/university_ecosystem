import { renderHook } from "@testing-library/react"
import type { DependencyList, EffectCallback } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type CallbackContract = {
  callback: unknown
  dependencies: unknown[]
}

const contracts = vi.hoisted(() => ({
  callbacks: [] as CallbackContract[],
  effects: [] as unknown[][],
}))

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react")
  return {
    ...actual,
    useCallback: <T extends (...args: never[]) => unknown>(
      callback: T,
      dependencies: DependencyList | undefined
    ): T => {
      const stableCallback = actual.useCallback(callback, dependencies ?? [])
      contracts.callbacks.push({
        callback: stableCallback,
        dependencies: dependencies ? [...dependencies] : [],
      })
      return stableCallback
    },
    useEffect: (effect: EffectCallback, dependencies?: DependencyList) => {
      contracts.effects.push(dependencies ? [...dependencies] : [])
      return actual.useEffect(effect, dependencies)
    },
  }
})

import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"

describe("useSessionCrypto lifecycle contracts", () => {
  beforeEach(() => {
    contracts.callbacks.length = 0
    contracts.effects.length = 0
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it("keeps callback and effect dependencies explicit and stable", () => {
    const { rerender, unmount } = renderHook(() => useSessionCrypto())

    expect(contracts.callbacks).toHaveLength(4)
    const [sendServiceWorkerMessage, sendSessionCacheUpdate, updateSessionSigningKey, ensure] =
      contracts.callbacks

    expect(sendServiceWorkerMessage?.dependencies).toEqual([])
    expect(sendSessionCacheUpdate?.dependencies).toEqual([sendServiceWorkerMessage?.callback])
    expect(updateSessionSigningKey?.dependencies).toEqual([sendSessionCacheUpdate?.callback])
    expect(ensure?.dependencies).toEqual([updateSessionSigningKey?.callback])

    expect(contracts.effects).toContainEqual([sendSessionCacheUpdate?.callback])
    expect(contracts.effects).toContainEqual([])

    rerender()
    expect(contracts.callbacks).toHaveLength(8)
    expect(contracts.effects).toHaveLength(4)
    expect(contracts.effects.slice(2)).toEqual(contracts.effects.slice(0, 2))

    unmount()
  })
})
