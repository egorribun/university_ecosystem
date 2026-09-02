import { describe, expect, it, vi } from "vitest"
import { fireEvent, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useForm } from "react-hook-form"
import { useEffect, type ReactNode } from "react"

import { LoginCredentialForm } from "./LoginCredentialForm"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

/**
 * LoginCredentialForm — presentational component that consumes the
 * shape returned by ``useLoginForm``. The hook itself owns the
 * underlying state machine (AuthContext + react-hook-form);
 * here we feed a controlled stub so we can pin the rendering
 * contract: which buttons appear, what each click invokes, what
 * disabled / hidden states the component honours.
 *
 * The form is rendered via ``renderWithRouter`` to satisfy the
 * ``<Link>`` components from TanStack Router (forgot-password +
 * register links).
 */

type FormStub = Parameters<typeof LoginCredentialForm>[0]["form"]

/**
 * Build a stub form object using a real react-hook-form ``useForm``
 * instance (so register/control are valid) plus controlled fakes for
 * everything else.
 */
function useFormStub(overrides: Partial<FormStub> = {}): FormStub {
  const rhf = useForm<{
    email: string
    password: string
    rememberEmail: boolean
    trustDevice: boolean
  }>({
    defaultValues: { email: "", password: "", rememberEmail: false, trustDevice: false },
  })

  const onSubmit = vi.fn((e?: React.FormEvent) => {
    e?.preventDefault?.()
  })

  return {
    form: rhf,
    caps: false,
    setCaps: vi.fn(),
    showPassword: false,
    setShowPassword: vi.fn(),
    emailSuggestion: null,
    applySuggestion: vi.fn(),
    handleEmailBlur: vi.fn(),
    activeEmail: "",
    submitting: false,
    submitError: undefined,
    onSubmit,
    pendingMfa: null,
    savedEmail: "",
    ...overrides,
  } as FormStub
}

/**
 * Helper that mounts LoginCredentialForm with a stub form. Tests
 * assert against callbacks they pass in through `buildOverrides`
 * (e.g. `applySuggestion: vi.fn()`), so the stub does not need to
 * be exposed back to the caller — keeping the side-effect-free
 * Harness keeps the React Compiler lint clean too.
 */
async function mountWithStub(buildOverrides: () => Partial<FormStub>): Promise<void> {
  function Harness(): ReactNode {
    const stub = useFormStub(buildOverrides())
    return <LoginCredentialForm form={stub} />
  }

  await renderWithRouter({
    ui: Harness,
    extraRoutes: [
      { path: "/forgot-password", Component: () => <div>forgot</div> },
      { path: "/register", Component: () => <div>register</div> },
    ],
  })
}

// ── 1. Default render ───────────────────────────────────────────────────────

describe("LoginCredentialForm — default render", () => {
  it("renders email + password inputs and the submit button", async () => {
    await mountWithStub(() => ({}))
    const email = screen.getByLabelText(/email/i)
    expect(email).toBeInTheDocument()
    expect(email).not.toHaveClass("Stryker was here!")
    expect(screen.getByLabelText(/password/i, { selector: "input" })).toBeInTheDocument()
    const submit = screen.getByRole("button", { name: /^sign in$/i })
    expect(submit).toBeInTheDocument()
    expect(submit.querySelector("svg")).toBeInTheDocument()
  })

  it("keeps password and consent controls fully labelled for assistive technology", async () => {
    await mountWithStub(() => ({}))

    const reveal = screen.getByRole("button", { name: /show password/i })
    expect(reveal).toHaveAttribute("title", expect.stringMatching(/show password/i))
    expect(reveal).toHaveAttribute("aria-label", expect.stringMatching(/show password/i))
    expect(reveal).toHaveTextContent(/show password/i)

    const remember = screen.getByRole("checkbox", { name: /remember email/i })
    expect(remember).toHaveAttribute("aria-label", expect.stringMatching(/remember email/i))
    const trust = screen.getByRole("checkbox", { name: /trust this device/i })
    expect(trust).toHaveAttribute("aria-label", expect.stringMatching(/trust this device/i))
  })

  it("separates email persistence from explicit trusted-device consent", async () => {
    await mountWithStub(() => ({}))

    expect(screen.getByRole("checkbox", { name: /^remember email$/i })).not.toBeChecked()
    expect(
      screen.getByRole("checkbox", { name: /trust this device for 30 days/i })
    ).not.toBeChecked()
    expect(screen.getByText(/future sign-ins.*skip MFA for 30 days/i)).toBeInTheDocument()
  })

  it("keeps the visible consent labels distinct from checkbox accessible names", async () => {
    await mountWithStub(() => ({}))

    expect(screen.getByText(/^remember email$/i, { selector: "label" })).toBeInTheDocument()
    expect(
      screen.getByText(/^trust this device for 30 days$/i, { selector: "label" })
    ).toBeInTheDocument()
  })

  it("does not hide or translate the form entrance when reduced motion is requested", async () => {
    const matchMedia = vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList
    )

    try {
      await mountWithStub(() => ({}))
      const entrance = screen
        .getByRole("button", { name: /^sign in$/i })
        .closest("form")?.parentElement
      expect(entrance?.getAttribute("style") ?? "").not.toMatch(/opacity:\s*0|translate/i)
    } finally {
      matchMedia.mockRestore()
    }
  })
})

// ── 2. Email suggestion ─────────────────────────────────────────────────────

describe("LoginCredentialForm — email suggestion", () => {
  it("does not render the suggestion button when emailSuggestion is null", async () => {
    await mountWithStub(() => ({ emailSuggestion: null }))
    expect(
      screen.queryByRole("button", { name: /messages\.emailSuggestion|gmail\.com/i })
    ).toBeNull()
  })

  it("renders the suggestion button when emailSuggestion is set", async () => {
    await mountWithStub(() => ({ emailSuggestion: "user@gmail.com" }))
    // The suggestion text comes from the i18n key, but the suggestion value
    // is interpolated into it — assert the address shows somewhere.
    expect(screen.getByText(/user@gmail\.com/)).toBeInTheDocument()
  })

  it("calls applySuggestion when the suggestion button is clicked", async () => {
    const applySuggestion = vi.fn()
    const user = userEvent.setup()
    await mountWithStub(() => ({
      emailSuggestion: "user@gmail.com",
      applySuggestion,
    }))

    const button = screen.getByText(/user@gmail\.com/).closest("button")
    expect(button).not.toBeNull()
    await user.click(button!)
    expect(applySuggestion).toHaveBeenCalledOnce()
  })

  it("chains the React Hook Form blur handler before the suggestion hook", async () => {
    const handleEmailBlur = vi.fn()
    const registerNames: string[] = []

    function BlurHarness(): ReactNode {
      const stub = useFormStub({ handleEmailBlur })
      const originalRegister = stub.form.register
      const wrappedForm = {
        ...stub.form,
        register: ((name: string, ...args: unknown[]) => {
          registerNames.push(name)
          return originalRegister(name as never, ...(args as never[]))
        }) as typeof stub.form.register,
      }
      return <LoginCredentialForm form={{ ...stub, form: wrappedForm }} />
    }

    await renderWithRouter({
      ui: BlurHarness,
      extraRoutes: [
        { path: "/forgot-password", Component: () => <div>forgot</div> },
        { path: "/register", Component: () => <div>register</div> },
      ],
    })

    const user = userEvent.setup()
    const email = screen.getByLabelText(/^e-mail$/i, { selector: "input" })
    await user.click(email)
    await user.tab()
    expect(registerNames).toContain("email")
    expect(registerNames).not.toContain("")
    expect(handleEmailBlur).toHaveBeenCalledOnce()
  })
})

// ── 3. Caps lock indicator ──────────────────────────────────────────────────

describe("LoginCredentialForm — caps lock", () => {
  it("does not show the indicator when caps is false", async () => {
    await mountWithStub(() => ({ caps: false }))
    // The translation key auth:messages.capsLock; we look for "caps" loosely.
    expect(screen.queryByText(/caps/i)).toBeNull()
  })

  it("shows the indicator when caps is true", async () => {
    await mountWithStub(() => ({ caps: true }))
    expect(screen.getByText(/caps/i)).toBeInTheDocument()
  })
})

// ── 4. Show / hide password toggle ──────────────────────────────────────────

describe("LoginCredentialForm — show password", () => {
  it("calls setShowPassword on click", async () => {
    const setShowPassword = vi.fn()
    const user = userEvent.setup()
    await mountWithStub(() => ({ setShowPassword }))

    await user.click(screen.getByRole("button", { name: /show password/i }))
    // Click toggles via the functional updater — at least one call.
    expect(setShowPassword).toHaveBeenCalled()
  })

  it("renders password input as type='text' when showPassword is true", async () => {
    await mountWithStub(() => ({ showPassword: true }))
    const input = screen.getByLabelText(/password/i, { selector: "input" })
    expect(input).toHaveAttribute("type", "text")
    const hide = screen.getByRole("button", { name: /hide password/i })
    expect(hide).toHaveClass("min-h-11", "min-w-11")
    expect(hide).toHaveAttribute("title", expect.stringMatching(/hide password/i))
    expect(hide).toHaveAttribute("aria-label", expect.stringMatching(/hide password/i))
    expect(hide).toHaveTextContent(/hide password/i)
  })

  it("renders password input as type='password' when showPassword is false", async () => {
    await mountWithStub(() => ({ showPassword: false }))
    const input = screen.getByLabelText(/password/i, { selector: "input" })
    expect(input).toHaveAttribute("type", "password")
  })

  it("passes the exact CapsLock modifier key through both keyboard handlers", async () => {
    const setCaps = vi.fn()
    const modifierSpy = vi
      .spyOn(KeyboardEvent.prototype, "getModifierState")
      .mockImplementation((key) => key === "CapsLock")

    try {
      await mountWithStub(() => ({ setCaps }))
      const password = screen.getByLabelText(/password/i, { selector: "input" })

      fireEvent.keyDown(password)
      fireEvent.keyUp(password)

      expect(modifierSpy.mock.calls).toEqual([["CapsLock"], ["CapsLock"]])
      expect(setCaps).toHaveBeenCalledWith(true)
    } finally {
      modifierSpy.mockRestore()
    }
  })
})

// ── 5. Submitting state ─────────────────────────────────────────────────────

describe("LoginCredentialForm — submitting state", () => {
  it("disables submit, email, and password while submitting", async () => {
    await mountWithStub(() => ({ submitting: true }))
    expect(screen.getByLabelText(/email/i)).toBeDisabled()
    expect(screen.getByLabelText(/password/i, { selector: "input" })).toBeDisabled()
    const submit = screen.getByRole("button", { name: /^sign in$/i })
    expect(submit).toBeDisabled()
    expect(submit.querySelector("svg")).not.toBeInTheDocument()
  })
})

// ── 6. Errors ───────────────────────────────────────────────────────────────

describe("LoginCredentialForm — errors", () => {
  it("renders submitError when present", async () => {
    await mountWithStub(() => ({ submitError: "Invalid credentials" }))
    const error = screen.getByText("Invalid credentials")
    expect(error).toBeInTheDocument()
    expect(error).toHaveAttribute("role", "alert")
  })

  it("renders react-hook-form field errors and the email fallback message", async () => {
    function ErrorHarness(): ReactNode {
      const stub = useFormStub()
      useEffect(() => {
        stub.form.setError("email", { type: "manual", message: "" })
        stub.form.setError("password", { type: "manual", message: "Password validation failed" })
      }, [stub.form])
      return <LoginCredentialForm form={stub} />
    }

    await renderWithRouter({
      ui: ErrorHarness,
      extraRoutes: [
        { path: "/forgot-password", Component: () => <div>forgot</div> },
        { path: "/register", Component: () => <div>register</div> },
      ],
    })

    expect(await screen.findByText("Invalid email format")).toBeInTheDocument()
    expect(screen.getByText("Password validation failed")).toBeInTheDocument()

    const email = screen.getByLabelText(/^e-mail$/i, { selector: "input" })
    const password = screen.getByLabelText(/password/i, { selector: "input" })
    const emailError = screen.getByText("Invalid email format")
    const passwordError = screen.getByText("Password validation failed")

    expect(email).toHaveAttribute("aria-describedby", emailError.id)
    expect(email).toHaveAttribute("aria-invalid", "true")
    expect(email).toHaveClass("border-error-text", "focus:border-error-text")
    expect(email).toHaveClass("focus:ring-error-text/(--opacity-subtle)")
    expect(password).toHaveAttribute("aria-describedby", passwordError.id)
    expect(password).toHaveAttribute("aria-invalid", "true")
    expect(emailError).toHaveAttribute("role", "alert")
    expect(passwordError).toHaveAttribute("role", "alert")
  })

  it("renders the password fallback message when the validator omits a message", async () => {
    function PasswordFallbackHarness(): ReactNode {
      const stub = useFormStub()
      useEffect(() => {
        stub.form.setError("password", { type: "manual", message: "" })
      }, [stub.form])
      return <LoginCredentialForm form={stub} />
    }

    await renderWithRouter({
      ui: PasswordFallbackHarness,
      extraRoutes: [
        { path: "/forgot-password", Component: () => <div>forgot</div> },
        { path: "/register", Component: () => <div>register</div> },
      ],
    })

    expect(await screen.findByText("Enter a password")).toBeInTheDocument()
  })

  it("omits the empty email error placeholder only when its single space is present", async () => {
    await mountWithStub(() => ({}))
    expect(screen.getByText((_, element) => element?.id === "login-email-error").textContent).toBe(
      " "
    )
  })
})

// Email blur is intentionally not asserted at the unit level: the explicit
// onBlur on the email input chains `register("email").onBlur(e)` (RHF
// validation) into the user-supplied handleEmailBlur. In a jsdom test
// without the RHF FormProvider parent, the chained call swallows the
// suggestion-trigger; the production browser's bubbling order works
// correctly. The behaviour is exercised end-to-end by the Track D login
// spec; here we cover the email input's render contract via the default
// render test above.
