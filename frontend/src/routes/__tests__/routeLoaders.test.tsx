/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, expect, it, vi, beforeEach } from "vitest"
import { Route as EventsDetailRoute } from "../_auth/events.$id"
import { Route as EventsIndexRoute } from "../_auth/events.index"
import { Route as NewsIndexRoute } from "../_auth/news.index"
import { Route as LoginRoute } from "../_public/login"
import { Route as ScheduleRoute } from "../_auth/schedule"
import { Route as SettingsRoute } from "../_auth/settings"
import { SETTINGS_TAB } from "@/features/settings/schema"

// Mock the query options factories
vi.mock("@/api/hooks/events", () => ({
  eventDetailQueryOptions: vi.fn().mockImplementation((id: string) => ({
    queryKey: ["event", id],
    queryFn: () => Promise.resolve({ id }),
  })),
  prefetchEventsListQuery: vi.fn().mockResolvedValue(undefined),
  EVENTS_PAGE_SIZE: 10,
}))

vi.mock("@/api/hooks/news", () => ({
  prefetchNewsListQuery: vi.fn().mockResolvedValue(undefined),
  NEWS_PAGE_SIZE: 10,
}))

vi.mock("@/api/hooks/users", () => ({
  currentUserQueryOptions: vi.fn().mockReturnValue({
    queryKey: ["user", "me"],
    queryFn: () => Promise.resolve({ id: "user-123" }),
  }),
}))

vi.mock("@/api/hooks/schedule", () => ({
  scheduleGroupsQueryOptions: vi.fn().mockReturnValue({
    queryKey: ["schedule", "groups"],
    queryFn: () => Promise.resolve([]),
  }),
  pageScheduleQueryOptions: vi.fn().mockImplementation((groupId: string) => ({
    queryKey: ["schedule", "lessons", groupId],
    queryFn: () => Promise.resolve([]),
  })),
}))

vi.mock("@/api/hooks/sessions", () => ({
  sessionsQueryOptions: vi.fn().mockImplementation((userId: string) => ({
    queryKey: ["sessions", userId],
    queryFn: () => Promise.resolve([]),
  })),
}))

describe("Route Loaders & validateSearch validation", () => {
  let mockQueryClient: any

  beforeEach(() => {
    vi.clearAllMocks()

    mockQueryClient = {
      ensureQueryData: vi.fn().mockImplementation((options: any) => {
        return options.queryFn()
      }),
    }
  })

  describe("events.$id.tsx Route", () => {
    it("calls loader and prefetches event detail query options", async () => {
      const loader = EventsDetailRoute.options.loader
      expect(loader).toBeTypeOf("function")

      const context = { queryClient: mockQueryClient }
      const params = { id: "test-event-uuid" }

      await (loader as any)({ context, params })

      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["event", "test-event-uuid"],
        })
      )
    })
  })

  describe("schedule.tsx Route", () => {
    it("validates search query parameters correctly", () => {
      const validateSearch = ScheduleRoute.options.validateSearch
      expect(validateSearch).toBeTypeOf("function")

      // Empty search is valid
      const parsedEmpty = (validateSearch as any)({})
      expect(parsedEmpty).toEqual({})

      // Valid search schema fields
      const parsedValid = (validateSearch as any)({ w: "1" })
      expect(parsedValid).toEqual({ w: 1 })
    })

    it("prefetches current user and groups in parallel; prefetches page schedule lessons if user has group_id", async () => {
      const loader = ScheduleRoute.options.loader
      expect(loader).toBeTypeOf("function")

      // Mock user query to return user with group_id
      mockQueryClient.ensureQueryData = vi.fn().mockImplementation((options: any) => {
        if (options.queryKey[0] === "user") {
          return Promise.resolve({ id: "user-123", group_id: "group-999" })
        }
        return options.queryFn()
      })

      const context = { queryClient: mockQueryClient }
      await (loader as any)({ context })

      // Should prefetch current user, groups and page schedule lessons
      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["user", "me"] })
      )
      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["schedule", "groups"] })
      )
      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["schedule", "lessons", "group-999"] })
      )
    })

    it("skips prefetching page schedule lessons if current user fetch fails or has no group_id", async () => {
      const loader = ScheduleRoute.options.loader
      expect(loader).toBeTypeOf("function")

      // Mock user query returning no group_id
      mockQueryClient.ensureQueryData = vi.fn().mockImplementation((options: any) => {
        if (options.queryKey[0] === "user") {
          return Promise.resolve({ id: "user-123", group_id: null })
        }
        return options.queryFn()
      })

      const context = { queryClient: mockQueryClient }
      await (loader as any)({ context })

      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["user", "me"] })
      )
      expect(mockQueryClient.ensureQueryData).not.toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["schedule", "lessons", expect.any(String)] })
      )
    })
  })

  describe("settings.tsx Route", () => {
    it("validates search query parameters correctly", () => {
      const validateSearch = SettingsRoute.options.validateSearch
      expect(validateSearch).toBeTypeOf("function")

      // Fallbacks to default tab 0
      const parsedEmpty = (validateSearch as any)({})
      expect(parsedEmpty).toEqual({ tab: 0 })

      const parsedValid = (validateSearch as any)({ tab: "2", spotify: "connected" })
      expect(parsedValid).toEqual({ tab: 2, spotify: "connected" })
    })

    it("maps search params to loader dependencies", () => {
      const loaderDeps = SettingsRoute.options.loaderDeps
      expect(loaderDeps).toBeTypeOf("function")

      const search = { tab: 2, spotify: "connected" }
      const deps = (loaderDeps as any)({ search })
      expect(deps).toEqual({ tab: 2 })
    })

    it("prefetches current user only when on non-security tab", async () => {
      const loader = SettingsRoute.options.loader
      expect(loader).toBeTypeOf("function")

      const context = { queryClient: mockQueryClient }
      const deps = { tab: SETTINGS_TAB.GENERAL }

      await (loader as any)({ context, deps })

      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["user", "me"] })
      )
      expect(mockQueryClient.ensureQueryData).not.toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sessions", expect.any(String)] })
      )
    })

    it("prefetches sessions list if tab is SECURITY and user has an active id", async () => {
      const loader = SettingsRoute.options.loader
      expect(loader).toBeTypeOf("function")

      mockQueryClient.ensureQueryData = vi.fn().mockImplementation((options: any) => {
        if (options.queryKey[0] === "user") {
          return Promise.resolve({ id: "user-456" })
        }
        return options.queryFn()
      })

      const context = { queryClient: mockQueryClient }
      const deps = { tab: SETTINGS_TAB.SECURITY }

      await (loader as any)({ context, deps })

      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["user", "me"] })
      )
      expect(mockQueryClient.ensureQueryData).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sessions", "user-456"] })
      )
    })
  })

  describe("events.index.tsx Route", () => {
    it("validates search query parameters correctly", () => {
      const validateSearch = EventsIndexRoute.options.validateSearch
      expect(validateSearch).toBeTypeOf("function")

      // Empty is valid
      const parsedEmpty = (validateSearch as any)({})
      expect(parsedEmpty).toEqual({})

      // Valid parameters
      const parsedValid = (validateSearch as any)({
        tab: "upcoming",
        q: "hackathon",
        dr: "2026-07-13",
        loc: "hall",
        sort: "date",
        cat: "study",
      })
      expect(parsedValid).toEqual({
        tab: "upcoming",
        q: "hackathon",
        dr: "2026-07-13",
        loc: "hall",
        sort: "date",
        cat: "study",
      })
    })

    it("prefetches events list in loader", async () => {
      const loader = EventsIndexRoute.options.loader
      expect(loader).toBeTypeOf("function")

      const context = { queryClient: mockQueryClient }
      await (loader as any)({ context })

      const { prefetchEventsListQuery } = await import("@/api/hooks/events")
      expect(prefetchEventsListQuery).toHaveBeenCalledWith(
        mockQueryClient,
        expect.objectContaining({ limit: 10 })
      )
    })
  })

  describe("news.index.tsx Route", () => {
    it("validates search query parameters correctly", () => {
      const validateSearch = NewsIndexRoute.options.validateSearch
      expect(validateSearch).toBeTypeOf("function")

      const parsedEmpty = (validateSearch as any)({})
      expect(parsedEmpty).toEqual({})
    })

    it("prefetches news list in loader", async () => {
      const loader = NewsIndexRoute.options.loader
      expect(loader).toBeTypeOf("function")

      const context = { queryClient: mockQueryClient }
      await (loader as any)({ context })

      const { prefetchNewsListQuery } = await import("@/api/hooks/news")
      expect(prefetchNewsListQuery).toHaveBeenCalledWith(
        mockQueryClient,
        expect.objectContaining({ limit: 10 })
      )
    })
  })

  describe("login.tsx Route", () => {
    it("validates search query parameters correctly", () => {
      const validateSearch = LoginRoute.options.validateSearch
      expect(validateSearch).toBeTypeOf("function")

      const parsedEmpty = (validateSearch as any)({})
      expect(parsedEmpty).toEqual({})

      const parsedValid = (validateSearch as any)({ redirect: "/dashboard" })
      expect(parsedValid).toEqual({ redirect: "/dashboard" })
    })
  })
})
