import { beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { useArticleNavigation } from "../useArticleNavigation"

const mocks = vi.hoisted(() => ({ getQueriesData: vi.fn() }))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ getQueriesData: mocks.getQueriesData }),
}))

describe("useArticleNavigation", () => {
  beforeEach(() => {
    mocks.getQueriesData.mockReset()
  })

  it("returns empty navigation when the current article is absent from cached pages", () => {
    mocks.getQueriesData.mockReturnValue([])

    const { result } = renderHook(() => useArticleNavigation("missing"))

    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
    expect(mocks.getQueriesData).toHaveBeenCalledWith({ queryKey: ["news", "list"] })
  })

  it("flattens cached pages, deduplicates IDs, and finds adjacent articles in order", () => {
    mocks.getQueriesData.mockReturnValue([
      [
        ["news", "list", "one"],
        {
          pages: [
            {
              items: [
                { id: "first", title: "First" },
                { id: "current", title: "Current" },
              ],
            },
          ],
        },
      ],
      [
        ["news", "list", "two"],
        {
          pages: [
            {
              items: [
                { id: "current", title: "Duplicate" },
                { id: "last", title: "Last" },
              ],
            },
          ],
        },
      ],
    ])

    const { result } = renderHook(() => useArticleNavigation("current"))

    expect(result.current).toEqual({
      prevId: "first",
      nextId: "last",
      prevTitle: "First",
      nextTitle: "Last",
    })
  })

  it("handles missing page data and first/last navigation boundaries", () => {
    mocks.getQueriesData.mockReturnValue([
      ["empty", {}],
      ["pages", { pages: [{}, { items: undefined }] }],
    ])
    expect(renderHook(() => useArticleNavigation("missing")).result.current).toEqual({
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    })

    mocks.getQueriesData.mockReturnValue([
      [
        "list",
        {
          pages: [
            {
              items: [
                { id: "first", title: "First" },
                { id: "last", title: "Last" },
              ],
            },
          ],
        },
      ],
    ])
    expect(renderHook(() => useArticleNavigation("first")).result.current).toEqual({
      prevId: null,
      nextId: "last",
      prevTitle: null,
      nextTitle: "Last",
    })
    expect(renderHook(() => useArticleNavigation("last")).result.current).toEqual({
      prevId: "first",
      nextId: null,
      prevTitle: "First",
      nextTitle: null,
    })
  })
})
