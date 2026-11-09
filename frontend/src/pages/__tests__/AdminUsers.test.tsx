import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { HttpResponse, http } from "msw"
import { QueryClient } from "@tanstack/react-query"

import AdminUsers from "@/pages/AdminUsers"
import { AuthContext } from "@/contexts/AuthContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import type { User } from "@/types/User"

import { server } from "@/tests/mocks/server"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const mockUsers = [
  {
    id: "1",
    full_name: "John Doe",
    email: "john@example.org",
    role: "student",
    group_id: "g1",
    is_active: true,
    avatar_url: null,
  },
  {
    id: "2",
    full_name: "Jane Smith",
    email: "jane@example.org",
    role: "teacher",
    group_id: null,
    is_active: true,
    avatar_url: null,
  },
]

const mockGroups = [
  { id: "g1", name: "Alpha" },
  { id: "g2", name: "Beta" },
]

const handlers = [
  http.get("*/users", ({ request }) => {
    const url = new URL(request.url)
    const fullName = url.searchParams.get("full_name")
    let filtered = [...mockUsers]
    if (fullName) {
      filtered = filtered.filter((u) => u.full_name.toLowerCase().includes(fullName.toLowerCase()))
    }
    return HttpResponse.json(filtered)
  }),
  http.get("*/groups", () => HttpResponse.json(mockGroups)),
  http.patch("*/users/:id", () => HttpResponse.json({ success: true })),
  http.delete("*/users/:id", () => HttpResponse.json({ success: true })),
]

const adminUser: User = {
  id: "admin-id",
  email: "admin@example.com",
  full_name: "Admin User",
  role: "admin",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: undefined,
  education_path: undefined,
  preferences: undefined,
  spotify_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
}

const authValue = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  user: adminUser,
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn(),
  requireMfa: vi.fn(),
  resetEtagCache: vi.fn(),
  authOperation: false,
}

const renderPage = async () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  const WrappedPage = () => (
    <AuthContext.Provider value={authValue}>
      <ThemeProvider>
        <AdminUsers />
      </ThemeProvider>
    </AuthContext.Provider>
  )

  return renderWithRouter({
    ui: WrappedPage,
    queryClient,
    authProvider: false,
  })
}

describe("AdminUsers page", () => {
  beforeEach(() => {
    server.use(...handlers)
  })

  it("renders users and groups", async () => {
    await renderPage()
    expect((await screen.findAllByText("John Doe"))[0]).toBeInTheDocument()
    expect((await screen.findAllByText("Jane Smith"))[0]).toBeInTheDocument()
    expect((await screen.findAllByText("Alpha"))[0]).toBeInTheDocument()
  })

  it("filters users by name", async () => {
    const requestedNames: string[] = []
    server.use(
      http.get("*/users", ({ request }) => {
        requestedNames.push(new URL(request.url).searchParams.get("full_name") ?? "")
        return HttpResponse.json(
          mockUsers.filter((u) =>
            u.full_name.includes(new URL(request.url).searchParams.get("full_name") ?? "")
          )
        )
      })
    )
    await renderPage()
    // Disambiguate from the "Full name, not sorted" column header button that
    // shares the same accessible label text.
    const filterInput = await screen.findByLabelText(/Full Name/i, { selector: "input" })
    await userEvent.type(filterInput, "John")

    await waitFor(() => expect(requestedNames).toContain("John"))
    await waitFor(() => expect(screen.queryByText("Jane Smith")).not.toBeInTheDocument())
    expect((await screen.findAllByText("John Doe"))[0]).toBeInTheDocument()
  })

  it("deletes the selected user through the API only after the confirmation dialog", async () => {
    const deletedIds: string[] = []
    server.use(
      http.delete("*/users/:id", ({ params }) => {
        deletedIds.push(String(params.id))
        return HttpResponse.json({ success: true })
      })
    )
    await renderPage()
    const deleteButtons = await screen.findAllByLabelText(/Delete user/i)
    await userEvent.click(deleteButtons[0]!)
    expect(deletedIds).toEqual([])

    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getAllByRole("button").at(-1)!)

    await waitFor(() => expect(deletedIds).toEqual(["1"]))
  })

  it("sends the chosen group for the user whose select changed", async () => {
    const user = userEvent.setup()
    const patches: { id: string; body: unknown }[] = []
    server.use(
      http.patch("*/users/:id", async ({ params, request }) => {
        patches.push({ id: String(params.id), body: await request.json() })
        return HttpResponse.json({ success: true })
      })
    )
    await renderPage()
    // The first select is for filters; the per-user selects follow. John Doe is in g1.
    const johnSelect = await waitFor(() => {
      const found = screen
        .getAllByRole("combobox")
        .find((s) => (s as HTMLSelectElement).value === "g1")
      expect(found).toBeDefined()
      return found as HTMLSelectElement
    })
    await user.selectOptions(johnSelect, "g2")

    await waitFor(() => expect(patches).toEqual([{ id: "1", body: { group_id: "g2" } }]))
  })
})
