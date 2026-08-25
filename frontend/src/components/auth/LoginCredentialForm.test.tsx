import { describe, expect, it, vi } from "vitest"
import { screen } from "@testing-library/react"
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
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i, { selector: "input" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeInTheDocument()
  })

  it("separates email persistence from explicit trusted-device consent", async () => {
    await mountWithStub(() => ({}))

    expect(screen.getByRole("checkbox", { name: /^remember email$/i })).not.toBeChecked()
    expect(
      screen.getByRole("checkbox", { name: /trust this device for 30 days/i })
    ).not.toBeChecked()
    expect(screen.getByText(/future sign-ins.*skip MFA for 30 days/i)).toBeInTheDocument()
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
  })

  it("renders password input as type='password' when showPassword is false", async () => {
    await mountWithStub(() => ({ showPassword: false }))
    const input = screen.getByLabelText(/password/i, { selector: "input" })
    expect(input).toHaveAttribute("type", "password")
  })
})

// ── 5. Submitting state ─────────────────────────────────────────────────────

describe("LoginCredentialForm — submitting state", () => {
  it("disables submit, email, and password while submitting", async () => {
    await mountWithStub(() => ({ submitting: true }))
    expect(screen.getByLabelText(/email/i)).toBeDisabled()
    expect(screen.getByLabelText(/password/i, { selector: "input" })).toBeDisabled()
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeDisabled()
  })
})

// ── 6. Errors ───────────────────────────────────────────────────────────────

describe("LoginCredentialForm — errors", () => {
  it("renders submitError when present", async () => {
    await mountWithStub(() => ({ submitError: "Invalid credentials" }))
    expect(screen.getByText("Invalid credentials")).toBeInTheDocument()
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
})

// Email blur is intentionally not asserted at the unit level: the explicit
// onBlur on the email input chains `register("email").onBlur(e)` (RHF
// validation) into the user-supplied handleEmailBlur. In a jsdom test
// without the RHF FormProvider parent, the chained call swallows the
// suggestion-trigger; the production browser's bubbling order works
// correctly. The behaviour is exercised end-to-end by the Track D login
// spec; here we cover the email input's render contract via the default
// render test above.
