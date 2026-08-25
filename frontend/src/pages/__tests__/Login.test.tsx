import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { axe } from "jest-axe"
import { QueryClient } from "@tanstack/react-query"

import Login from "../Login"
import { server } from "@/tests/mocks/server"
import { testUser } from "@/tests/mocks/handlers"
import i18n from "../../i18n/config"
import { createTestQueryClient, renderWithRouter } from "@/tests/helpers/renderWithRouter"
import { useAuthStore } from "@/stores/useAuthStore"

const tAuth = (key: string, options?: Record<string, unknown>) => i18n.t(`auth:${key}`, options)
const matchText = (text: string) => (content: string) => content.startsWith(text)

const clients: QueryClient[] = []

interface RenderLoginOptions {
  /**
   * Wave 177 SW2 — opt-out of the default `/users/me → 401` msw override.
   * Default behavior (skipMeOverride: false): block /users/me so the
   * W177 SW1 reactive useEffect in Login.tsx (subscribes to
   * useAuthStore.user → navigate to /dashboard) doesn't fire mid-test.
   * Login UI tests don't care about authed state — they verify form
   * behavior. Set skipMeOverride: true for the dedicated W174 §Honesty
   * #3 regression test that exercises the redirect explicitly.
   */
  skipMeOverride?: boolean
  /**
   * Wave 179 SW4 — override initialPath (default "/login") to inject
   * search.redirect query param for race-regression test of W177 §Honesty #3.
   * E.g., "/login?redirect=http%3A%2F%2Flocalhost%2Fevents" exercises the
   * canonical TanStack `search.redirect` path through useLoginFlow +
   * Login.tsx useEffect + _public.tsx useEffect.
   */
  initialPath?: string
  /**
   * Wave 179 SW4 — override extraRoutes (default just /dashboard) to add
   * routes the redirect target may navigate to (e.g., /events). When
   * navigate({ to: "/events" }) fires, the test asserts on rendered content
   * from this extra route.
   */
  extraRoutes?: Array<{ path: string; Component: React.ComponentType }>
}

const renderLogin = (options: RenderLoginOptions = {}) => {
  const client = createTestQueryClient()
  clients.push(client)
  if (!options.skipMeOverride) {
    // Wave 177 SW2 — block /users/me so Login.tsx W177 SW1 useEffect
    // doesn't fire during form-behavior tests. See handlers.ts:373 for
    // the default mock that returns testUser.
    server.use(http.get("*/users/me", () => HttpResponse.json(null, { status: 401 })))
  }
  return renderWithRouter({
    ui: Login,
    path: "/login",
    initialPath: options.initialPath ?? "/login",
    extraRoutes: options.extraRoutes ?? [
      { path: "/dashboard", Component: () => <div>Welcome!</div> },
    ],
    queryClient: client,
  })
}

describe("Login page", () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem("ue:language", "en")
  })

  afterEach(() => {
    localStorage.clear()
    clients.splice(0).forEach((client) => client.clear())
    // Wave 177 SW2 — reset useAuthStore between tests. Pre-W177 this was
    // silent because Login.tsx didn't react to user state; W177 SW1
    // useEffect makes prior-test user-state pollution observable
    // (redirect-to-/dashboard fires immediately on mount). Match the
    // initial state from useAuthStore.ts:22-26 (loading:true optimistic).
    useAuthStore.setState({
      user: null,
      loading: true,
      pendingMfa: null,
      authOperation: false,
    })
  })

  it("blocks submission for invalid email", async () => {
    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "invalid")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    expect(await screen.findByText(tAuth("messages.invalidEmail"))).toBeInTheDocument()
  })

  it("submits credentials and redirects on success", async () => {
    const captured: Array<{ username: string | null; password: string | null }> = []
    server.use(
      http.post("*/auth/login", async ({ request }) => {
        const body = await request.text()
        const params = new URLSearchParams(body)
        captured.push({ username: params.get("username"), password: params.get("password") })
        return HttpResponse.json({
          access_token: "token-123",
          token_type: "bearer",
          user: testUser,
          session: { signing_key: "test-key-123" },
        })
      })
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByLabelText(tAuth("actions.showPassword")))
    await user.click(screen.getByLabelText(tAuth("actions.hideCredential")))
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
    expect(captured).toEqual([{ username: "user@example.com", password: "secret123" }])
  }, 15000)

  it("redirects authed user away from /login (W174 §Honesty #3, W177 SW1)", async () => {
    // Wave 177 SW1+SW2 regression test. With skipMeOverride:true, renderLogin
    // does NOT add the /users/me → 401 override → default msw (handlers.ts:373)
    // returns testUser → AuthProvider's useProfileSync populates useAuthStore
    // → Login.tsx W177 SW1 useEffect observes user transition null→testUser
    // → fires navigate({to:"/dashboard", replace:true}) → extraRoutes' /dashboard
    // → "Welcome!" rendered. Regression-guards W174 SW1 (route guards read
    // live Zustand) AND W177 SW1 (Login.tsx reactive useEffect) from future
    // reverts.
    await renderLogin({ skipMeOverride: true })

    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument(), {
      timeout: 5_000,
    })
  })

  it("honors search.redirect param across authed-user redirect (W177 §Honesty #3, W179 SW4)", async () => {
    // Wave 179 SW4 race regression test. Closes W177 §Honesty #3: unauth user
    // deep-links to /events → _auth.tsx:47 beforeLoad throws redirect to
    // /login?redirect=http://localhost/events → user auths → Login.tsx W177
    // SW1 useEffect observes user transition null→testUser. Pre-W179 the
    // useEffect hardcoded /dashboard target, ignoring search.redirect →
    // user lands on /dashboard not /events (intended destination lost).
    // W179 SW4 fix: useEffect reads `useRouterState({select: s.location.search})`
    // + calls resolveRedirectPath → returns "/events" pathname → navigate
    // target is /events → "Events page" rendered (NOT "Welcome!" from /dashboard).
    //
    // skipMeOverride:true → useProfileSync populates testUser → useEffect fires
    // initialPath sets search.redirect explicitly
    // extraRoutes adds /events to the in-memory router (so navigation can resolve)
    // Test uses RELATIVE path "/events" (vs production writer's absolute URL
    // `location.href`). Helper accepts both forms — relative-path branch
    // returns the input verbatim, absolute-URL branch extracts pathname via
    // URL constructor + same-origin check. Test runs the relative branch to
    // keep the assertion environment-agnostic re: jsdom window.location.origin
    // (which equals "http://localhost" in default jsdom and matches the
    // helper's same-origin check — but the relative branch sidesteps that
    // dependency entirely for test isolation).
    await renderLogin({
      skipMeOverride: true,
      initialPath: "/login?redirect=/events",
      extraRoutes: [
        { path: "/dashboard", Component: () => <div>Welcome!</div> },
        { path: "/events", Component: () => <div>Events page</div> },
      ],
    })

    await waitFor(() => expect(screen.getByText("Events page")).toBeInTheDocument(), {
      timeout: 5_000,
    })
    // Negative assertion: /dashboard should NOT render (would happen pre-W179 SW4)
    expect(screen.queryByText("Welcome!")).not.toBeInTheDocument()
  })

  it("returns server errors to the user", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json({ detail: tAuth("login.error") }, { status: 401 })
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    expect(await screen.findByText(tAuth("login.error"))).toBeInTheDocument()
  })

  it("shows lockout messaging with retry information", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json(
          {
            detail:
              "Too many failed attempts. Your account is temporarily locked. Try again in 2 minutes.",
          },
          { status: 423, headers: { "Retry-After": "120" } }
        )
      )
    )

    const user = userEvent.setup()
    await renderLogin()

    const emailInput = screen.getByLabelText(matchText(tAuth("fields.email")), {
      selector: 'input[type="email"]',
    })

    await user.type(emailInput, "user@example.com")
    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "secret123"
    )
    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    const message = await screen.findByText(
      (content) =>
        content.includes("temporarily locked") && content.includes("Try again in 2 minutes")
    )
    expect(message).toBeInTheDocument()
  })

  it("transitions to MFA verification when additional challenges are required", async () => {
    // Wave 177 SW2 — removed vestigial `/users/me → mfa-user` override.
    // The MFA UI trigger is the POST /auth/login 202 response (handlers.ts:655-664
    // matches mfa@example.com + Password123 → returns PendingMfaResponse → useAuthApi
    // calls updatePendingMfa → useMfaFlow.loginChallenge becomes truthy → MfaChallengeView
    // renders). The previous /users/me override pre-populated useAuthStore.user, which
    // post-W177 SW1 would trigger Login.tsx's reactive useEffect → premature redirect
    // before the user could submit credentials. With the override removed, /users/me
    // resolves to 401 via renderLogin's default helper override → user stays null →
    // useEffect doesn't fire → MFA flow proceeds normally via POST /auth/login.
    const user = userEvent.setup()
    await renderLogin()

    // Wait for initial auth check to complete
    await waitFor(() => expect(screen.queryByText(/loading|загрузка/i)).not.toBeInTheDocument(), {
      timeout: 1000,
    }).catch(() => {}) // Ignore if no loading indicator

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.email")), {
        selector: 'input[type="email"]',
      }),
      "mfa@example.com"
    )

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "Password123"
    )

    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await screen.findByText(tAuth("mfa.verifyTitle"))

    const otpInputs = await screen.findAllByRole("textbox", { name: /digit/i })
    await user.click(otpInputs[0]!)
    await user.keyboard("123456")
    // OtpEntry auto-submits on complete, so we just wait for the result
    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
  }, 15000)

  it("displays errors for invalid OTP attempts and allows retry", async () => {
    // Wave 177 SW2 — same rationale as the previous MFA test: removed vestigial
    // `/users/me → mfa-user` override. MFA flow triggers via POST /auth/login 202.
    const user = userEvent.setup()
    await renderLogin()

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.email")), {
        selector: 'input[type="email"]',
      }),
      "mfa@example.com"
    )

    await user.type(
      screen.getByLabelText(matchText(tAuth("fields.password")), {
        selector: 'input[type="password"]',
      }),
      "Password123"
    )

    await user.click(screen.getByRole("button", { name: tAuth("actions.signIn") }))

    await screen.findByText(tAuth("mfa.verifyTitle"))

    const otpInputs = await screen.findAllByRole("textbox", { name: /digit/i })
    await user.click(otpInputs[0]!)
    await user.keyboard("000000")
    // OtpEntry auto-submits on complete
    await screen.findByText(/Invalid verification code|Неверный код/i)

    // After error, user clears input and types new code
    // Note: OtpEntry component auto-clears on error via useEffect, but mfaError prop stays set
    // which blocks auto-submit. We need to wait for the input to be cleared, then type new code
    // and click the button manually since auto-submit is blocked
    await waitFor(() => expect(otpInputs[0]!).toHaveValue(""))
    await user.click(otpInputs[0]!)
    await user.keyboard("123456")
    // Must click button since error prop blocks auto-submit
    await user.click(screen.getByRole("button", { name: /Verify|Подтвердить/i }))
    await waitFor(() => expect(screen.getByText("Welcome!")).toBeInTheDocument())
  }, 15000)

  it("meets basic accessibility requirements", async () => {
    const { container } = await renderLogin()
    // Wait for AuthProvider and Login component to settle (initial check/loading)
    await waitFor(() => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument())

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
