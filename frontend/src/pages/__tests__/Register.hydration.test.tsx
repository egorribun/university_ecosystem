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
import Register from "../Register"

type LinkStubProps = {
  to: string
  children: ReactNode
  className?: string
}

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }))

// Keep Register, native controls, RHF, Valibot, and motion real. Substitute
// only navigation and the HTTP boundary, as in the adjacent auth contracts.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigate,
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
        <Register />
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

it("keeps every server-rendered registration control inert before handlers attach", () => {
  const serverMarkup = document.createElement("div")
  serverMarkup.innerHTML = renderServerMarkup()

  expect(serverMarkup.querySelector("form")?.method).toBe("post")
  for (const name of ["full_name", "email", "password", "confirmPassword"]) {
    expect(serverMarkup.querySelector(`input[name="${name}"]`)).not.toBeNull()
  }
  // Four text/credential inputs, one role trigger, two reveal buttons, submit.
  const controls = serverMarkup.querySelectorAll("input, button")
  expect(controls).toHaveLength(8)
  for (const control of controls) {
    expect(control).toBeDisabled()
  }
  expect(serverMarkup.querySelector('a[href="/login"]')).not.toBeNull()
})

it("hydrates without recovery and submits the first valid registration once", async () => {
  let releaseRegistration!: () => void
  const registrationCompletion = new Promise<void>((resolve) => {
    releaseRegistration = resolve
  })
  const post = vi.spyOn(api, "post").mockImplementation(async () => {
    await registrationCompletion
    return {
      data: { status: "ok" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
  })
  const recoverableErrors: unknown[] = []
  const container = document.createElement("div")
  let root: Root | undefined

  try {
    container.innerHTML = renderServerMarkup()
    document.body.append(container)
    await act(async () => {
      root = hydrateRoot(container, <Harness />, {
        onRecoverableError: (error) => recoverableErrors.push(error),
      })
    })

    const ui = within(container)
    const registrationControls = () => {
      const controls = container.querySelectorAll("input, button")
      expect(controls).toHaveLength(8)
      return controls
    }
    for (const control of registrationControls()) {
      expect(control).toBeEnabled()
    }
    expect(recoverableErrors).toEqual([])
    expect(post).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()

    const user = userEvent.setup()
    const submit = ui.getByRole("button", { name: i18n.t("auth:actions.signUp") })
    await user.click(submit)
    for (const field of ["name", "email", "password", "confirm-password"]) {
      await waitFor(() =>
        expect(container.querySelector(`#register-${field}-error`)).toHaveAttribute("role", "alert")
      )
    }
    expect(post).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()

    const fullName = ui.getByLabelText(i18n.t("auth:fields.name"), {
      exact: true,
      selector: "input",
    })
    const email = ui.getByLabelText(i18n.t("auth:fields.email"), {
      exact: true,
      selector: "input",
    })
    const password = ui.getByLabelText(i18n.t("auth:fields.password"), {
      exact: true,
      selector: "input",
    })
    const confirmation = ui.getByLabelText(i18n.t("auth:fields.confirmPassword"), {
      exact: true,
      selector: "input",
    })
    const submittedPassword = crypto.randomUUID()
    await user.type(fullName, "Hydration Student")
    await user.type(email, "person@example.test")
    await user.type(password, submittedPassword)
    await user.type(confirmation, submittedPassword)
    expect(fullName).toHaveValue("Hydration Student")
    expect(email).toHaveValue("person@example.test")
    expect(password).toHaveValue(submittedPassword)
    expect(confirmation).toHaveValue(submittedPassword)

    await user.click(submit)
    await waitFor(() => expect(post).toHaveBeenCalledOnce())
    expect(post).toHaveBeenCalledWith("/auth/register", {
      full_name: "Hydration Student",
      email: "person@example.test",
      password: submittedPassword,
      role: "student",
      invite_code: "",
    })
    expect(navigate).not.toHaveBeenCalled()
    expect(submit).toHaveAttribute("aria-busy", "true")
    for (const control of registrationControls()) {
      expect(control).toBeDisabled()
    }
    expect(fullName).toHaveValue("Hydration Student")
    expect(email).toHaveValue("person@example.test")
    expect(password).toHaveValue(submittedPassword)
    expect(confirmation).toHaveValue(submittedPassword)

    await act(async () => releaseRegistration())
    await waitFor(() => expect(navigate).toHaveBeenCalledExactlyOnceWith({ to: "/login" }))
    expect(post).toHaveBeenCalledOnce()
    for (const control of registrationControls()) {
      expect(control).toBeEnabled()
    }
    expect(recoverableErrors).toEqual([])
  } finally {
    try {
      await act(async () => releaseRegistration())
    } finally {
      try {
        await act(async () => root?.unmount())
      } finally {
        container.remove()
        post.mockRestore()
      }
    }
  }
})
