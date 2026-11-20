import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react"
import { useEffect, type ReactNode } from "react"
import { expect } from "vitest"
import api from "@/api/client"
import { createQueryClient, getQueryCacheIdentity, setQueryCacheIdentity } from "@/app/queryClient"
import { useAuth } from "@/contexts/AuthContext"
import Schedule from "@/pages/Schedule"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import type { User } from "@/types/User"
import { scheduleGroupsQueryOptions } from "@/api/hooks/schedule"

vi.mock("@/db/lazy", () => ({
  getDatabaseLazily: async () => ({
    schedule: { bulkUpsert: async () => {} },
    notes: { find: () => ({ exec: async () => [] }) },
  }),
}))
vi.mock("@/components/motion/PageFadeIn", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const accountA: User = {
  ...testUser,
  id: "10000000-0000-4000-8000-000000000001",
  role: "student",
  group_id: "group-a",
}
const accountB: User = {
  ...testUser,
  id: "20000000-0000-4000-8000-000000000002",
  role: "student",
  group_id: "group-b",
}
const lessonA = {
  id: "lesson-a",
  weekday: "Monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:00",
  subject: "Group A lesson",
  teacher: "Teacher",
  room: "101",
  lesson_type: "lecture",
  group_id: "group-a",
}
const lessonB = { ...lessonA, id: "lesson-b", subject: "Group B lesson", group_id: "group-b" }

async function mountSchedule(initial: User = accountA) {
  let account = initial
  let pendingProfile: Promise<{ data: User }> | null = null
  let pendingGroupB: Promise<{ data: (typeof lessonB)[] }> | null = null
  let latestAuth: ReturnType<typeof useAuth> | undefined
  const requests: string[] = []
  vi.spyOn(api, "post").mockResolvedValue({ data: {} } as never)
  const deleteRequest = vi.spyOn(api, "delete").mockResolvedValue({ data: {} } as never)
  vi.spyOn(api, "get").mockImplementation(async (url) => {
    const path = String(url)
    requests.push(path)
    if (path === "/users/me") return (pendingProfile ?? { data: account }) as never
    if (path === "/auth/session/signing-key") return { data: {} } as never
    if (path === "/groups")
      return {
        data: [
          { id: "group-a", name: "Group A" },
          { id: "group-b", name: "Group B" },
        ],
      } as never
    if (path === "/schedule/group-a") return { data: [lessonA] } as never
    if (path === "/schedule/group-b") return (pendingGroupB ?? { data: [lessonB] }) as never
    return { data: [] } as never
  })
  const Probe = () => {
    const auth = useAuth()
    useEffect(() => {
      latestAuth = auth
    }, [auth])
    return <Schedule />
  }
  const client = createQueryClient()
  const view = await renderWithRouter({ ui: Probe, path: "/schedule", queryClient: client })
  await waitFor(() => expect(latestAuth?.user?.id).toBe(initial.id))
  expect(await screen.findByText("Group A lesson")).toBeInTheDocument()
  return {
    get auth() {
      if (!latestAuth) throw new Error("Schedule auth provider was not mounted")
      return latestAuth
    },
    requests,
    client,
    deleteRequest,
    setAccount(value: User) {
      account = value
    },
    deferProfile() {
      let resolveProfile!: (value: { data: User }) => void
      pendingProfile = new Promise((resolve) => {
        resolveProfile = resolve
      })
      return (value: User) => {
        account = value
        resolveProfile({ data: value })
        pendingProfile = null
      }
    },
    deferGroupB() {
      let resolveGroup!: (value: { data: (typeof lessonB)[] }) => void
      pendingGroupB = new Promise((resolve) => {
        resolveGroup = resolve
      })
      return () => {
        resolveGroup({ data: [lessonB] })
        pendingGroupB = null
      }
    },
    close() {
      view.unmount()
      client.clear()
    },
  }
}

describe("Schedule account ownership", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    setQueryCacheIdentity(null)
    useAuthStore.setState({ user: null, loading: true })
    localStorage.setItem("token", "synthetic-session")
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))
    )
  })
  afterEach(() => {
    cleanup()
    useAuthStore.setState({ user: null, loading: true })
    setQueryCacheIdentity(null)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("switches directly to the new account's group without a retired-group request", async () => {
    const app = await mountSchedule()
    try {
      localStorage.setItem(
        "sched:group-b",
        JSON.stringify({ version: 1, timestamp: Date.now(), data: [lessonA] })
      )
      const before = app.requests.length
      const finishGroupB = app.deferGroupB()
      app.setAccount(accountB)
      act(() => app.auth.setUser(accountB))
      await waitFor(() => expect(getQueryCacheIdentity()).toBe(accountB.id))
      await waitFor(() => expect(app.requests.slice(before)).toContain("/schedule/group-b"))
      expect(app.requests.slice(before)).not.toContain("/schedule/group-a")
      expect(screen.queryByText("Group A lesson")).not.toBeInTheDocument()
      await act(async () => finishGroupB())
      expect(await screen.findByText("Group B lesson")).toBeInTheDocument()
    } finally {
      app.close()
    }
  })

  it("hides previous lessons and pending actions through an unconfirmed transition", async () => {
    const app = await mountSchedule({ ...accountA, role: "teacher" })
    try {
      const deleteButton = document.getElementById("delete-lesson-lesson-a")
      expect(deleteButton).not.toBeNull()
      fireEvent.click(deleteButton!)
      expect(await screen.findByRole("alertdialog")).toBeInTheDocument()
      const before = app.requests.length
      const finishProfile = app.deferProfile()
      let refresh: Promise<void> | undefined
      act(() => {
        refresh = app.auth.refresh()
      })
      await waitFor(() => expect(app.auth.loading).toBe(true))
      expect(screen.queryByText("Group A lesson")).not.toBeInTheDocument()
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
      expect(document.getElementById("delete-lesson-lesson-a")).toBeNull()
      await act(async () => {
        finishProfile(accountB)
        await refresh
      })
      expect(await screen.findByText("Group B lesson")).toBeInTheDocument()
      expect(app.requests.slice(before)).not.toContain("/schedule/group-a")
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
      expect(app.deleteRequest).not.toHaveBeenCalled()
    } finally {
      app.close()
    }
  })

  it("retains a same-account selected group through refresh without a duplicate fetch", async () => {
    const teacher = { ...accountA, role: "teacher" as const }
    const app = await mountSchedule(teacher)
    try {
      fireEvent.click(screen.getByRole("combobox"))
      fireEvent.mouseDown(await screen.findByRole("option", { name: "Group B" }), { button: 0 })
      expect(await screen.findByText("Group B lesson")).toBeInTheDocument()
      const before = app.requests.filter((path) => path === "/schedule/group-b").length
      const finishProfile = app.deferProfile()
      let refresh: Promise<void> | undefined
      act(() => {
        refresh = app.auth.refresh()
      })
      await waitFor(() => expect(app.auth.loading).toBe(true))
      expect(screen.queryByText("Group B lesson")).not.toBeInTheDocument()
      await act(async () => {
        finishProfile(teacher)
        await refresh
      })
      expect(await screen.findByText("Group B lesson")).toBeInTheDocument()
      expect(app.requests.filter((path) => path === "/schedule/group-b")).toHaveLength(before)
      act(() => app.auth.setUser({ ...teacher, full_name: "Updated same account" }))
      await waitFor(() => expect(app.auth.user?.full_name).toBe("Updated same account"))
      expect(screen.getByText("Group B lesson")).toBeInTheDocument()
      expect(app.requests.filter((path) => path === "/schedule/group-b")).toHaveLength(before)
    } finally {
      app.close()
    }
  })

  it("closes a pending deletion when its selected group disappears", async () => {
    const app = await mountSchedule({ ...accountA, role: "teacher" })
    try {
      const deleteButton = document.getElementById("delete-lesson-lesson-a")
      expect(deleteButton).not.toBeNull()
      fireEvent.click(deleteButton!)
      expect(await screen.findByRole("alertdialog")).toBeInTheDocument()
      act(() => {
        app.client.setQueryData(scheduleGroupsQueryOptions().queryKey, [
          { id: "group-b", name: "Group B" },
        ])
      })
      expect(await screen.findByText("Group B lesson")).toBeInTheDocument()
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
      expect(app.deleteRequest).not.toHaveBeenCalled()
    } finally {
      app.close()
    }
  })
})
