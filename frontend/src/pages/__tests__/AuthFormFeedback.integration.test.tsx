import { randomUUID } from "node:crypto"
import type { ComponentType } from "react"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query"
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { AppProviders } from "@/AppProviders"
import i18n from "@/i18n/config"
import { useAuthStore } from "@/stores/useAuthStore"
import { createTestQueryClient } from "@/tests/helpers/renderWithRouter"
import { server } from "@/tests/mocks/server"
import Login from "../Login"
import ResetPassword from "../ResetPassword"

const clients: QueryClient[] = []

function freshPassword() {
  return `Aa1!${randomUUID()}`
}

// Exercise the production providers, forms, hooks, and Axios interceptors.
// In particular, the application mounts a persistent, initially empty alert
// portal alongside the form. The lightweight page helper omits that portal.
async function renderPublicForm(Component: ComponentType, path: string, initialPath = path) {
  const client = createTestQueryClient()
  clients.push(client)
  const rootRoute = createRootRoute({
    component: () => (
      <AppProviders>
        <Outlet />
      </AppProviders>
    ),
  })
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path,
    component: () => <Component />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
    context: { queryClient: client, auth: { isAuth: false, user: null, loading: false } },
  })
  await router.load()
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router as never} />
    </QueryClientProvider>
  )
  await waitFor(() => expect(useAuthStore.getState().loading).toBe(false))
  return router
}

describe("public form feedback with production providers", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })
    server.use(http.get("*/users/me", () => HttpResponse.json(null, { status: 401 })))
  })

  afterEach(() => {
    cleanup()
    clients.splice(0).forEach((client) => client.clear())
    localStorage.clear()
  })

  it.each(["ru", "en"])(
    "shows one generic %s login error inside the submitted form",
    async (language) => {
      localStorage.setItem("ue:language", language)
      await i18n.changeLanguage(language)
      const email = "rejected@example.com"
      const password = freshPassword()
      const submitted: string[] = []
      server.use(
        http.post("*/auth/login", async ({ request }) => {
          submitted.push(await request.text())
          return HttpResponse.json({ detail: `Rejected ${email}: ${password}` }, { status: 401 })
        })
      )
      const router = await renderPublicForm(Login, "/login")
      const backgroundAlert = screen.getByRole("alert")
      expect(backgroundAlert).toBeEmptyDOMElement()
      expect(backgroundAlert).toHaveClass("sr-only")

      const user = userEvent.setup()
      await user.type(screen.getByLabelText(i18n.t("auth:fields.email")), email)
      await user.type(
        screen.getByLabelText(i18n.t("auth:fields.password"), { exact: true }),
        password
      )
      const submit = screen.getByRole("button", { name: i18n.t("auth:actions.signIn") })
      await user.click(submit)
      await waitFor(() => expect(submit).toBeEnabled())

      const form = submit.closest("form")!
      const feedback = within(form).getByRole("alert")
      expect(screen.getAllByRole("alert")).toEqual([feedback, backgroundAlert])
      expect(backgroundAlert).toBeEmptyDOMElement()
      expect(feedback).toBeVisible()
      expect(feedback.textContent).toBe(i18n.t("auth:login.error"))
      expect(document.body).not.toHaveTextContent(email)
      expect(document.body).not.toHaveTextContent(password)
      expect(submitted).toHaveLength(1)
      expect(new URLSearchParams(submitted[0]).get("username")).toBe(email)
      expect(new URLSearchParams(submitted[0]).get("password")).toBe(password)
      expect(router.state.location.pathname).toBe("/login")
      expect(useAuthStore.getState().user).toBeNull()
    }
  )

  it("shows the rejected reset error inside its form without exposing the consumed token", async () => {
    localStorage.setItem("ue:language", "en")
    const token = "consumed-reset-token"
    const password = freshPassword()
    const submitted: unknown[] = []
    server.use(
      http.post("*/password/reset", async ({ request }) => {
        submitted.push(await request.json())
        return HttpResponse.json({ detail: "Invalid or expired token" }, { status: 400 })
      })
    )
    const router = await renderPublicForm(
      ResetPassword,
      "/reset-password",
      `/reset-password?token=${token}`
    )
    await waitFor(() => expect(router.state.location.search).not.toHaveProperty("token"))
    const backgroundAlert = screen.getByRole("alert")
    expect(backgroundAlert).toBeEmptyDOMElement()
    expect(backgroundAlert).toHaveClass("sr-only")

    const user = userEvent.setup()
    await user.type(
      screen.getByLabelText(i18n.t("auth:fields.password"), { exact: true }),
      password
    )
    await user.type(
      screen.getByLabelText(i18n.t("auth:fields.confirmPassword"), { exact: true }),
      password
    )
    const submit = screen.getByRole("button", { name: i18n.t("auth:reset.saveButton") })
    await user.click(submit)
    await waitFor(() => expect(submit).toBeEnabled())

    const form = submit.closest("form")!
    const feedback = within(form).getByRole("alert")
    expect(screen.getAllByRole("alert")).toEqual([feedback, backgroundAlert])
    expect(backgroundAlert).toBeEmptyDOMElement()
    expect(feedback).toBeVisible()
    expect(feedback.textContent).toBe("Invalid or expired token")
    expect(document.body).not.toHaveTextContent(token)
    expect(screen.queryByText(i18n.t("auth:reset.successTitle"))).not.toBeInTheDocument()
    expect(submitted).toEqual([{ token, password }])
  })
})
