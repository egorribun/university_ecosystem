import { act, StrictMode, type ReactNode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, it, vi } from "vitest"
import { useForm, type SubmitHandler } from "react-hook-form"

import type { LoginValues } from "@/features/auth/schemas"
import { LoginCredentialForm } from "./LoginCredentialForm"

type FormStub = Parameters<typeof LoginCredentialForm>[0]["form"]

// Keep the form, native controls, and RHF real; navigation and translated
// labels are presentation-only dependencies of this hydration regression.
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    children,
    className,
  }: {
    to: string
    children: ReactNode
    className?: string
  }) => (
    <a href={to} className={className}>
      {children}
    </a>
  ),
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

let root: Root | undefined
let container: HTMLDivElement | undefined

function Harness({
  onValid,
  submitting = false,
}: {
  onValid: SubmitHandler<LoginValues>
  submitting?: boolean
}) {
  const rhf = useForm<LoginValues>({
    defaultValues: { email: "", password: "", rememberEmail: false, trustDevice: false },
  })
  const form: FormStub = {
    form: rhf,
    caps: false,
    setCaps: () => undefined,
    showPassword: false,
    setShowPassword: () => undefined,
    emailSuggestion: "person@example.test",
    applySuggestion: () => undefined,
    handleEmailBlur: async () => undefined,
    activeEmail: "",
    submitting,
    submitError: undefined,
    onSubmit: rhf.handleSubmit(onValid),
    pendingMfa: null,
    savedEmail: "",
  }
  return <LoginCredentialForm form={form} />
}

function renderServerMarkup(onValid: SubmitHandler<LoginValues>): string {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window")!
  Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
  try {
    return renderToString(
      <StrictMode>
        <Harness onValid={onValid} />
      </StrictMode>
    )
  } finally {
    Object.defineProperty(globalThis, "window", originalWindow)
  }
}

afterEach(async () => {
  await act(async () => root?.unmount())
  root = undefined
  container?.remove()
  container = undefined
})

it("keeps every server-rendered form control disabled before handlers attach", () => {
  const serverMarkup = document.createElement("div")
  serverMarkup.innerHTML = renderServerMarkup(vi.fn())

  expect(serverMarkup.querySelector("form")?.method).toBe("post")
  expect(serverMarkup.querySelector("#password")).toHaveAttribute("name", "password")
  const controls = serverMarkup.querySelectorAll("input, button")
  expect(controls).toHaveLength(7)
  for (const control of controls) {
    expect(control).toBeDisabled()
  }
  expect(serverMarkup.querySelector('a[href="/forgot-password"]')).not.toBeNull()
  expect(serverMarkup.querySelector('a[href="/register"]')).not.toBeNull()
})

it("hydrates without recovery and handles the first credential click exactly once", async () => {
  const onValid = vi.fn<SubmitHandler<LoginValues>>()
  const recoverableErrors: unknown[] = []
  container = document.createElement("div")
  container.innerHTML = renderServerMarkup(onValid)
  document.body.append(container)

  await act(async () => {
    root = hydrateRoot(
      container!,
      <StrictMode>
        <Harness onValid={onValid} />
      </StrictMode>,
      { onRecoverableError: (error) => recoverableErrors.push(error) }
    )
  })
  const ui = within(container)
  expect(recoverableErrors).toEqual([])
  expect(container.querySelector("form")?.method).toBe("post")
  for (const control of container.querySelectorAll("input, button")) {
    expect(control).toBeEnabled()
  }

  const user = userEvent.setup()
  await user.type(ui.getByRole("textbox", { name: "auth:fields.email" }), "person@example.test")
  await user.type(
    ui.getByLabelText("auth:fields.password", { selector: "input" }),
    "first-password"
  )
  await user.click(ui.getByRole("button", { name: "auth:actions.signIn" }))
  await waitFor(() => expect(onValid).toHaveBeenCalledOnce())
  expect(onValid.mock.calls[0]?.[0]).toEqual({
    email: "person@example.test",
    password: "first-password",
    rememberEmail: false,
    trustDevice: false,
  })

  await act(async () => {
    root!.render(
      <StrictMode>
        <Harness onValid={onValid} submitting />
      </StrictMode>
    )
  })
  for (const control of container.querySelectorAll("input, button")) {
    expect(control).toBeDisabled()
  }
  expect(recoverableErrors).toEqual([])
})
