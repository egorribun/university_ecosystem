import { act, StrictMode, type ReactNode } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LazyMotion, domAnimation } from "framer-motion"
import { expect, it, vi } from "vitest"

import axios from "@/api/client"
import i18n from "@/i18n/config"
import ForgotPassword from "../ForgotPassword"

type LinkStubProps = {
  to: string
  children: ReactNode
  className?: string
}

// Keep the page, native controls, RHF, validation, and motion provider real.
// Only navigation and the HTTP boundary are substituted in this regression.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
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
        <ForgotPassword />
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

it("keeps the server-rendered email and submit controls inert before handlers attach", () => {
  const serverMarkup = document.createElement("div")
  serverMarkup.innerHTML = renderServerMarkup()

  const controls = serverMarkup.querySelectorAll("input, button")
  expect(controls).toHaveLength(2)
  expect(serverMarkup.querySelector("#forgot-email-input")).toHaveAttribute("name", "email")
  for (const control of controls) {
    expect(control).toBeDisabled()
  }
  expect(serverMarkup.querySelector('a[href="/login"]')).not.toBeNull()
})

it("hydrates without recovery and submits the first valid email exactly once", async () => {
  const submittedEmail = "person@example.test"
  const post = vi.spyOn(axios, "post").mockResolvedValue({ data: { status: "ok" } })
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
    const input = ui.getByRole("textbox", { name: i18n.t("auth:fields.email") })
    const submit = ui.getByRole("button", { name: i18n.t("auth:forgot.sendLink") })
    expect(recoverableErrors).toEqual([])
    await waitFor(() => expect(input).toBeEnabled())
    expect(submit).toBeDisabled()
    expect(post).not.toHaveBeenCalled()

    const user = userEvent.setup()
    await user.type(input, submittedEmail)
    await waitFor(() => expect(submit).toBeEnabled())
    expect(input).toHaveValue(submittedEmail)
    await user.click(submit)
    await waitFor(() => expect(post).toHaveBeenCalledOnce())
    expect(post).toHaveBeenCalledWith("/password/forgot", { email: submittedEmail })
    expect(recoverableErrors).toEqual([])
  } finally {
    try {
      await act(async () => root?.unmount())
    } finally {
      container.remove()
      post.mockRestore()
    }
  }
})
