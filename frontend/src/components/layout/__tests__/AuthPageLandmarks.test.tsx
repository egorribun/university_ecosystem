import { act, cleanup, screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { QueryClient } from "@tanstack/react-query"

import { MainLayout } from "../MainLayout"
import Login from "@/pages/Login"
import Register from "@/pages/Register"
import { server } from "@/tests/mocks/server"
import { createTestQueryClient, renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { useAuthStore } from "@/stores/useAuthStore"
import i18n from "@/i18n/config"

const LoginWithMainLayout = () => (
  <MainLayout>
    <Login />
  </MainLayout>
)
const RegisterWithMainLayout = () => (
  <MainLayout>
    <Register />
  </MainLayout>
)

let activeQueryClient: QueryClient | null = null
let previousAuth: ReturnType<typeof useAuthStore.getState>

beforeEach(() => {
  previousAuth = useAuthStore.getState()
  server.resetHandlers()
  localStorage.clear()
  localStorage.setItem("ue:language", "en")
  act(() => {
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
  })
})

afterEach(() => {
  cleanup()
  activeQueryClient?.clear()
  activeQueryClient = null
  server.resetHandlers()
  localStorage.clear()
  act(() => {
    useAuthStore.setState(previousAuth)
  })
})

async function renderLogin() {
  server.use(http.get("*/users/me", () => HttpResponse.json(null, { status: 401 })))
  const queryClient = createTestQueryClient()
  activeQueryClient = queryClient
  await renderWithRouter({
    ui: LoginWithMainLayout,
    path: "/login",
    initialPath: "/login",
    queryClient,
  })
  await waitFor(() => expect(useAuthStore.getState().loading).toBe(false), { timeout: 5_000 })
}

async function renderRegister() {
  const queryClient = createTestQueryClient()
  activeQueryClient = queryClient
  await renderWithRouter({
    ui: RegisterWithMainLayout,
    path: "/register",
    initialPath: "/register",
    queryClient,
    authProvider: false,
  })
}

function expectSingleMainContainingAuthPage(title: string) {
  expect(screen.getAllByRole("main")).toHaveLength(1)
  const main = screen.getByRole("main")
  expect(main).toHaveAttribute("id", "main-content")
  expect(main).toContainElement(screen.getByRole("heading", { level: 1, name: title }))
  const authRegion = within(main).getByRole("region", { name: title })
  expect(authRegion.querySelectorAll("form")).toHaveLength(1)
  expect(authRegion).toHaveClass("auth-shell")
  expect(main).toContainElement(authRegion)
}

describe("auth page landmarks under MainLayout", () => {
  it("renders login with one main landmark", async () => {
    await renderLogin()
    expectSingleMainContainingAuthPage(i18n.t("auth:login.title"))
  })

  it("renders registration with one main landmark", async () => {
    await renderRegister()
    expectSingleMainContainingAuthPage(i18n.t("auth:register.title"))
  })
})
