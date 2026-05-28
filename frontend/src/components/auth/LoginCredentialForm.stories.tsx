import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { LazyMotion, domAnimation } from "framer-motion"
import { LoginCredentialForm } from "./LoginCredentialForm"
import type { useLoginForm } from "@/hooks/auth/useLoginFlow"
import type { LoginValues } from "@/features/auth/schemas"

// Wave 194 SW2 — LoginCredentialForm Storybook fixture.
//
// The component consumes the entire `useLoginForm()` return as a single `form`
// prop (LoginCredentialForm.tsx:11-12) — it never calls the coupled hook
// itself, so a story just supplies a tsc-typed mock object. The one field that
// must be live is `form.form` (a react-hook-form instance: register/control/
// formState power the inputs), so the harness calls a real `useForm<LoginValues>`
// + real useState for caps/showPassword (the component uses functional updaters).
// The `<Link>`s need RouterProvider (global preview decorator ✓); `<FadeIn>`
// uses framer-motion `m.*` → the decorator adds LazyMotion (W124 SW1 mirror).
//
// Variants: Default, WithError (root submitError), WithEmailSuggestion (typo
// banner), NoPasskey (webauthnSupported false → hides passkey button), DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          className="auth-theme flex items-center justify-center"
          style={{ background: "var(--bg-page)", minHeight: "100vh", padding: "2rem" }}
        >
          <div style={{ width: "100%", maxWidth: 480 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

function LoginHarness({ overrides }: { overrides?: Partial<ReturnType<typeof useLoginForm>> }) {
  const form = useForm<LoginValues>({
    defaultValues: { email: "", password: "", trustDevice: false },
  })
  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const mockForm: ReturnType<typeof useLoginForm> = {
    form,
    savedEmail: "",
    caps,
    setCaps,
    showPassword,
    setShowPassword,
    emailSuggestion: null,
    applySuggestion: () => {},
    handleEmailBlur: async () => {},
    activeEmail: "",
    submitting: false,
    submitError: undefined,
    passkeyError: null,
    webauthnSupported: true,
    trustDevice: false,
    setTrustDevice: () => {},
    handlePasskeyLogin: async () => {},
    onSubmit: form.handleSubmit(async () => {}),
    pendingMfa: null,
    ...overrides,
  }

  return <LoginCredentialForm form={mockForm} />
}

const meta: Meta<typeof LoginCredentialForm> = {
  title: "Auth/LoginCredentialForm",
  component: LoginCredentialForm,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof LoginCredentialForm>

export const Default: Story = {
  render: () => <LoginHarness />,
  decorators: [themed(false)],
}

export const WithError: Story = {
  render: () => <LoginHarness overrides={{ submitError: "Invalid email or password" }} />,
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Root submit error rendered in the assertive `aria-live` slot." },
    },
  },
}

export const WithEmailSuggestion: Story = {
  render: () => <LoginHarness overrides={{ emailSuggestion: "student@guu.ru" }} />,
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Fuzzy email-domain suggestion banner with the apply-suggestion CTA." },
    },
  },
}

export const NoPasskey: Story = {
  render: () => <LoginHarness overrides={{ webauthnSupported: false }} />,
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "webauthnSupported=false hides the 'Sign in with Passkey' button." },
    },
  },
}

export const DarkMode: Story = {
  render: () => <LoginHarness />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
