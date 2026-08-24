import { render, screen } from "@testing-library/react"
import { Suspense } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/pages/Dashboard", () => ({
  default: () => <div data-testid="dashboard-page" />,
}))
vi.mock("@/pages/Login", () => ({
  default: () => <div data-testid="login-page" />,
}))
vi.mock("@/pages/Register", () => ({
  default: () => <div data-testid="register-page" />,
}))
vi.mock("@/pages/ForgotPassword", () => ({
  default: () => <div data-testid="forgot-password-page" />,
}))
vi.mock("@/pages/ResetPassword", () => ({
  default: () => <div data-testid="reset-password-page" />,
}))

import { Route as DashboardRoute } from "../_auth/dashboard"
import { Route as ForgotPasswordRoute } from "../_public/forgot-password"
import { Route as LoginRoute } from "../_public/login"
import { Route as RegisterRoute } from "../_public/register"
import { Route as ResetPasswordTokenRoute } from "../_public/reset-password.$token"
import { Route as ResetPasswordRoute } from "../_public/reset-password"

const lazyRoutes = [
  ["dashboard-page", DashboardRoute],
  ["login-page", LoginRoute],
  ["register-page", RegisterRoute],
  ["forgot-password-page", ForgotPasswordRoute],
  ["reset-password-page", ResetPasswordRoute],
  ["reset-password-page", ResetPasswordTokenRoute],
] as const

describe("lazy route components", () => {
  it.each(lazyRoutes)("loads %s", async (testId, route) => {
    const Component = route.options.component!

    render(
      <Suspense fallback={<div data-testid="route-loading" />}>
        <Component />
      </Suspense>
    )

    expect(await screen.findByTestId(testId)).toBeInTheDocument()
  })
})
