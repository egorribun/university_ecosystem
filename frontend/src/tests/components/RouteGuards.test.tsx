import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { AdminRoute, PrivateRoute } from "@/components/RouteGuards"
import { checkA11y } from "../axeTest"

const mockUseAuth = vi.fn()

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}))

beforeEach(() => {
  mockUseAuth.mockReset()
})

afterEach(() => {
  mockUseAuth.mockReset()
})

describe("PrivateRoute", () => {
  test("shows an accessible loading fallback while authentication is resolving", async () => {
    mockUseAuth.mockReturnValue({ isAuth: false, loading: true, user: null })

    const { container } = render(
      <MemoryRouter>
        <PrivateRoute>
          <div>Secret content</div>
        </PrivateRoute>
      </MemoryRouter>
    )

    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(screen.getAllByText(/loading/i)[0]).toBeInTheDocument()
    expect(container.querySelector("main#main")).not.toBeNull()
    expect(container.querySelector("header")).not.toBeNull()

    await checkA11y(container)
  })

  test("renders protected content when the user is authenticated", () => {
    mockUseAuth.mockReturnValue({ isAuth: true, loading: false, user: { role: "student" } })

    render(
      <MemoryRouter>
        <PrivateRoute>
          <div>Protected dashboard</div>
        </PrivateRoute>
      </MemoryRouter>
    )

    expect(screen.getByText("Protected dashboard")).toBeInTheDocument()
  })

  test("redirects unauthenticated users to the login page", () => {
    mockUseAuth.mockReturnValue({ isAuth: false, loading: false, user: null })

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <div>Dashboard content</div>
              </PrivateRoute>
            }
          />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText("Login Page")).toBeInTheDocument()
  })
})

describe("AdminRoute", () => {
  test("shows the loading indicator while the admin state is resolving", async () => {
    mockUseAuth.mockReturnValue({ isAuth: true, loading: true, user: { role: "admin" } })

    const { container } = render(
      <AdminRoute>
        <div>Admin content</div>
      </AdminRoute>
    )

    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")

    await checkA11y(container)
  })

  test("redirects non-admin users to the dashboard", () => {
    mockUseAuth.mockReturnValue({ isAuth: true, loading: false, user: { role: "student" } })

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div>Secret admin data</div>
              </AdminRoute>
            }
          />
          <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText("Dashboard Page")).toBeInTheDocument()
  })

  test("renders children for authenticated administrators", () => {
    mockUseAuth.mockReturnValue({ isAuth: true, loading: false, user: { role: "admin" } })

    render(
      <AdminRoute>
        <div>Stories admin</div>
      </AdminRoute>
    )

    expect(screen.getByText("Stories admin")).toBeInTheDocument()
  })
})
