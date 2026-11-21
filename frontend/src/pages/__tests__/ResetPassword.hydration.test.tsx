type _MockedModuleType1 = typeof import("@tanstack/react-router")
import { act, StrictMode, type ReactNode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AxiosHeaders } from "axios"
import { LazyMotion, domAnimation } from "framer-motion"
import { expect, it, vi } from "vitest"

import api from "@/api/client"
import i18n from "@/i18n/config"
import ResetPassword from "../ResetPassword"

type LinkStubProps = {
  to: string
  children: ReactNode
  className?: string
}

const route = vi.hoisted(() => ({
  location: {
    pathname: "/reset-password",
    search: {},
    state: { key: "test-entry" },
    hash: "",
  },
  params: {} as { token?: string },
  matched: { fullPath: "/reset-password" },
  navigate: vi.fn().mockResolvedValue(undefined),
}))

// The real page, inputs, RHF, validation, and motion are rendered; only the
// router boundary and external HTTP calls are substituted.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<_MockedModuleType1>()),
  useLocation: () => route.location,
  useNavigate: () => route.navigate,
  useRouter: () => ({
    getMatchedRoutes: () => [[], route.params, route.matched],
    history: { subscribe: () => () => undefined },
    state: { location: route.location },
  }),
  Link: ({ to, children, className }: LinkStubProps) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))

function Harness() {
  return (
    <StrictMode>
      <LazyMotion features={domAnimation}>
        <ResetPassword />
      </LazyMotion>
    </StrictMode>
  )
}

function renderServerMarkup(): string {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window")!
  Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
  try {
    return renderToString(<Harness />)
  } finally {
    Object.defineProperty(globalThis, "window", originalWindow)
  }
}

it.each([
  { label: "without a token", path: "/reset-password", token: undefined },
  { label: "with a token route", path: "/reset-password/example", token: "example" },
])("keeps $label controls inert in server-rendered markup", ({ path, token }) => {
  route.location.pathname = path
  route.location.hash = ""
  route.params = token ? { token } : {}
  route.matched = { fullPath: token ? "/reset-password/$token" : "/reset-password" }

  const serverMarkup = document.createElement("div")
  serverMarkup.innerHTML = renderServerMarkup()

  expect(serverMarkup.querySelector("form")).toHaveAttribute("data-csrf", "header")
  expect(serverMarkup.querySelector("form")?.method).toBe("post")
  expect(serverMarkup.querySelector('input[name="password"]')).not.toBeNull()
  expect(serverMarkup.querySelector('input[name="confirmPassword"]')).not.toBeNull()
  const controls = serverMarkup.querySelectorAll("input, button")
  expect(controls).toHaveLength(5)
  for (const control of controls) expect(control).toBeDisabled()
  expect(serverMarkup.querySelector('a[href="/forgot-password"]')).not.toBeNull()
})

it("hydrates a fragment-token reset, validates, and completes one pending submission", async () => {
  route.location.pathname = "/reset-password"
  route.location.hash = ""
  route.params = {}
  route.matched = { fullPath: "/reset-password" }
  const recoverableErrors: unknown[] = []
  const container = document.createElement("div")
  let root: Root | undefined
  let finishRequest!: () => void
  const requestCompletion = new Promise<void>((resolve) => {
    finishRequest = resolve
  })
  const post = vi.spyOn(api, "post").mockImplementation(async () => {
    await requestCompletion
    return {
      data: { status: "ok" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
  })
  const fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response("", { status: 503 }))

  try {
    // URL fragments are available to the browser, but never to the server.
    container.innerHTML = renderServerMarkup()
    route.location.hash = "token=example-token"
    document.body.append(container)
    await act(async () => {
      root = hydrateRoot(container, <Harness />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })

    const ui = within(container)
    const controls = () => container.querySelectorAll("input, button")
    for (const control of controls()) expect(control).toBeEnabled()
    expect(recoverableErrors).toEqual([])
    expect(post).not.toHaveBeenCalled()

    const user = userEvent.setup()
    const submit = ui.getByRole("button", { name: i18n.t("auth:reset.saveButton") })
    await user.click(submit)
    await waitFor(() => expect(container.querySelectorAll('[role="alert"]')).toHaveLength(2))
    expect(post).not.toHaveBeenCalled()

    const password = ui.getByLabelText(i18n.t("auth:fields.password"), { selector: "input" })
    const confirmation = ui.getByLabelText(i18n.t("auth:fields.confirmPassword"), {
      selector: "input",
    })
    const examplePassword = crypto.randomUUID() + "Aa1!"
    await user.type(password, examplePassword)
    await user.type(confirmation, examplePassword)
    const reveal = container.querySelector<HTMLButtonElement>("#reset-password-toggle")!
    await user.click(reveal)
    expect(password).toHaveAttribute("type", "text")
    await user.click(reveal)
    expect(password).toHaveAttribute("type", "password")

    await user.dblClick(submit)
    await waitFor(() => expect(post).toHaveBeenCalledOnce())
    expect(post).toHaveBeenCalledWith("/password/reset", {
      token: "example-token",
      password: examplePassword,
    })
    expect(submit).toHaveAttribute("aria-busy", "true")
    for (const control of controls()) expect(control).toBeDisabled()
    expect(password).toHaveValue(examplePassword)
    expect(confirmation).toHaveValue(examplePassword)

    await act(async () => finishRequest())
    const success = await ui.findByRole("heading", { name: i18n.t("auth:reset.successTitle") })
    expect(success).toHaveFocus()
    expect(post).toHaveBeenCalledOnce()
    expect(recoverableErrors).toEqual([])
  } finally {
    await act(async () => finishRequest())
    await act(async () => root?.unmount())
    container.remove()
    post.mockRestore()
    fetchSpy.mockRestore()
  }
})
