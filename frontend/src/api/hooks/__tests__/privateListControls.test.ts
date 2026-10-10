import { describe, expect, it } from "vitest"

import { pickPrivateListControls } from "../privateListControls"

describe("private list option boundary", () => {
  it("preserves documented timing, retry, refetch, error and pagination controls", () => {
    const allowed = {
      enabled: false,
      staleTime: 0,
      gcTime: 100,
      retry: 0,
      retryDelay: () => 10,
      retryOnMount: false,
      networkMode: "offlineFirst",
      refetchInterval: 100,
      refetchIntervalInBackground: true,
      refetchOnMount: "always",
      refetchOnReconnect: false,
      refetchOnWindowFocus: false,
      throwOnError: false,
      notifyOnChangeProps: ["data"],
      getPreviousPageParam: () => null,
      maxPages: 2,
      meta: { name: "feed" },
      subscribed: true,
    }
    expect(pickPrivateListControls(allowed)).toEqual(allowed)
  })

  it("ignores data providers and key overrides without even reading their values", () => {
    const options = { enabled: true }
    for (const key of [
      "select",
      "placeholderData",
      "initialData",
      "initialDataUpdatedAt",
      "structuralSharing",
      "persister",
      "queryFn",
      "queryKey",
      "queryHash",
      "queryKeyHashFn",
      "behavior",
      "initialPageParam",
      "getNextPageParam",
    ]) {
      Object.defineProperty(options, key, {
        get: () => {
          throw new Error(`Read forbidden ${key}`)
        },
      })
    }
    expect(pickPrivateListControls(options)).toEqual({ enabled: true })
  })

  it("leaves defaults intact when options or individual values are undefined", () => {
    expect(pickPrivateListControls(undefined)).toEqual({})
    expect(pickPrivateListControls({ enabled: undefined, staleTime: undefined })).toEqual({})
  })
})
