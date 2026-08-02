import { renderHook, act } from "@testing-library/react"
import fc from "fast-check"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"

// ---------------------------------------------------------------------------
// Mock TanStack Router BEFORE importing the hook.
// useURLState depends on useSearch and useNavigate from @tanstack/react-router.
// We provide a minimal stub so the hook can be tested in isolation from a
// real router context.
// ---------------------------------------------------------------------------

const mockSearch = vi.fn(() => ({}))
const mockNavigateFn = vi.fn()
const mockNavigate = vi.fn(() => mockNavigateFn)

vi.mock("@tanstack/react-router", () => ({
  useSearch: () => mockSearch(),
  useNavigate: () => mockNavigate(),
}))

// Import AFTER the mock is registered
import { useURLState } from "../useURLState"

type TestSearch = { tab?: string; q?: string; page?: number }

describe("useURLState", () => {
  beforeEach(() => {
    mockSearch.mockReturnValue({})
    mockNavigate.mockReturnValue(mockNavigateFn)
    mockNavigateFn.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  // ---------------------------------------------------------------------------
  // params — reflects current search
  // ---------------------------------------------------------------------------
  it("exposes current search params as 'params'", () => {
    mockSearch.mockReturnValue({ tab: "active", q: "math" })
    const { result } = renderHook(() => useURLState<TestSearch>())
    expect(result.current.params).toEqual({ tab: "active", q: "math" })
  })

  it("returns empty object when no search params", () => {
    mockSearch.mockReturnValue({})
    const { result } = renderHook(() => useURLState<TestSearch>())
    expect(result.current.params).toEqual({})
  })

  // ---------------------------------------------------------------------------
  // setParam — single key update
  // ---------------------------------------------------------------------------
  it("calls navigate with replace:true and viewTransition:false on setParam", () => {
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParam("tab", "archive")
    })

    expect(mockNavigateFn).toHaveBeenCalledWith(
      expect.objectContaining({ replace: true, viewTransition: false })
    )
  })

  it("adds a new param via setParam search updater", () => {
    mockSearch.mockReturnValue({ tab: "active" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParam("q", "physics")
    })

    // Extract the search updater function from the navigate call
    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active" })
    expect(updatedSearch).toEqual({ tab: "active", q: "physics" })
  })

  it("removes a param from URL when value is empty string", () => {
    mockSearch.mockReturnValue({ tab: "archive", q: "math" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParam("q", "")
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "archive", q: "math" })
    expect(updatedSearch).not.toHaveProperty("q")
  })

  it("removes a param when value is undefined", () => {
    mockSearch.mockReturnValue({ tab: "active", q: "bio" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParam("q", undefined)
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active", q: "bio" })
    expect(updatedSearch).not.toHaveProperty("q")
  })

  it("removes a param when value is null", () => {
    mockSearch.mockReturnValue({ tab: "active", q: "chem" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParam("q", null)
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active", q: "chem" })
    expect(updatedSearch).not.toHaveProperty("q")
  })

  // ---------------------------------------------------------------------------
  // setParams — batch update
  // ---------------------------------------------------------------------------
  it("updates multiple params at once via setParams", () => {
    mockSearch.mockReturnValue({ tab: "active" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParams({ q: "math", tab: "archive" })
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active" })
    expect(updatedSearch).toEqual({ tab: "archive", q: "math" })
  })

  it("removes params set to empty string in batch update", () => {
    mockSearch.mockReturnValue({ tab: "active", q: "bio" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParams({ q: "" })
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active", q: "bio" })
    expect(updatedSearch).not.toHaveProperty("q")
    expect(updatedSearch).toHaveProperty("tab", "active")
  })

  it("removes params set to null in batch update", () => {
    mockSearch.mockReturnValue({ tab: "active", q: "chem" })
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParams({ q: null as unknown as string })
    })

    const navigateArg = mockNavigateFn.mock.calls[0]?.[0]
    if (!navigateArg) throw new Error("mockNavigateFn was not called")
    const updatedSearch = navigateArg.search({ tab: "active", q: "chem" })
    expect(updatedSearch).not.toHaveProperty("q")
  })

  it("uses replace:true and viewTransition:false on setParams", () => {
    const { result } = renderHook(() => useURLState<TestSearch>())

    act(() => {
      result.current.setParams({ tab: "all" })
    })

    expect(mockNavigateFn).toHaveBeenCalledWith(
      expect.objectContaining({ replace: true, viewTransition: false })
    )
  })

  it("preserves the URL update contract for arbitrary batch values", () => {
    const valueArbitrary = fc.oneof(
      fc.string(),
      fc.integer(),
      fc.constant(null),
      fc.constant(undefined)
    )
    const updatesArbitrary = fc.dictionary(fc.constantFrom("tab", "q", "page"), valueArbitrary, {
      maxKeys: 3,
    })

    fc.assert(
      fc.property(updatesArbitrary, (updates) => {
        mockNavigateFn.mockClear()
        const { result } = renderHook(() => useURLState<TestSearch>())
        const previous = { tab: "active", q: "seed", page: 2 }

        act(() => {
          result.current.setParams(updates as Partial<TestSearch>)
        })

        const navigateArg = mockNavigateFn.mock.calls.at(-1)?.[0]
        if (!navigateArg) throw new Error("mockNavigateFn was not called")

        const expected: Record<string, unknown> = { ...previous }
        for (const [key, value] of Object.entries(updates)) {
          if (value === "" || value === undefined || value === null) {
            delete expected[key]
          } else {
            expected[key] = value
          }
        }

        expect(navigateArg.search(previous)).toEqual(expected)
        expect(navigateArg.replace).toBe(true)
        expect(navigateArg.viewTransition).toBe(false)
      })
    )
  })
})
