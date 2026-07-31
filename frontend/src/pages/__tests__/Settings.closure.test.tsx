import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  initialSearch: { tab: 0 as number | undefined, spotify: undefined as string | undefined },
  navigate: vi.fn(),
  setSearch: null as ((updater: (previous: Record<string, unknown>) => unknown) => void) | null,
  action: vi.fn(async () => undefined),
}))

vi.mock("@tanstack/react-router", async () => {
  const React = await import("react")
  return {
    useSearch: () => {
      const [search, setSearch] = React.useState(mocks.initialSearch)
      mocks.setSearch = (updater) => {
        setSearch((previous) => updater(previous) as typeof mocks.initialSearch)
      }
      return search
    },
    useNavigate: () => mocks.navigate,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: vi.fn() },
  }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => false,
}))

vi.mock("@/components/layout/PageLayout", () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}))

vi.mock("@/components/settings", async () => {
  const React = await import("react")
  return {
    SettingsBackdrop: (props: Record<string, boolean>) => (
      <div data-testid="settings-backdrop" data-flags={JSON.stringify(props)} />
    ),
    Tabs: ({
      value,
      onChange,
      children,
    }: {
      value: number
      onChange: (event: unknown, next: number) => void
      children: React.ReactNode
    }) => (
      <div role="tablist">
        {React.Children.map(children, (child, index) =>
          React.isValidElement(child)
            ? React.cloneElement(
                child as React.ReactElement<{
                  selected?: boolean
                  onClick?: () => void
                }>,
                {
                  selected: value === index,
                  onClick: () => onChange(null, index),
                }
              )
            : child
        )}
      </div>
    ),
    Tab: ({
      label,
      selected,
      onClick,
    }: {
      label: string
      selected?: boolean
      onClick?: () => void
    }) => (
      <button type="button" role="tab" aria-selected={selected} onClick={onClick}>
        {label}
      </button>
    ),
    Snackbar: ({
      open,
      onClose,
      children,
    }: {
      open: boolean
      onClose: () => void
      children: React.ReactNode
    }) =>
      open ? (
        <div role="status">
          <button type="button" onClick={onClose}>
            dismiss snackbar
          </button>
          {children}
        </div>
      ) : null,
  }
})

vi.mock("@/components/mfa/StepUpDialog", () => ({
  StepUpDialog: ({
    open,
    onClose,
    onCompleted,
  }: {
    open: boolean
    onClose: () => void
    onCompleted: () => void
  }) =>
    open ? (
      <div role="dialog" aria-label="step up">
        <button type="button" onClick={onCompleted}>
          complete step up
        </button>
        <button type="button" onClick={onClose}>
          close step up
        </button>
      </div>
    ) : null,
}))

vi.mock("@/pages/settings/SettingsGeneral", () => ({
  SettingsGeneral: ({
    setSnackbar,
  }: {
    setSnackbar: (value: { text: string; severity?: "info" }) => void
  }) => (
    <div>
      <h2>general panel</h2>
      <button type="button" onClick={() => setSnackbar({ text: "info message", severity: "info" })}>
        show info snackbar
      </button>
    </div>
  ),
}))

vi.mock("@/pages/settings/SettingsProfile", () => ({
  SettingsProfile: () => <h2>profile panel</h2>,
}))

vi.mock("@/pages/settings/SettingsIntegrations", () => ({
  SettingsIntegrations: () => <h2>integrations panel</h2>,
}))

vi.mock("@/pages/settings/SettingsSecurity", () => ({
  SettingsSecurity: ({
    openStepUpFor,
    isActive,
  }: {
    openStepUpFor: (action: () => Promise<void>) => void
    isActive: boolean
  }) =>
    isActive ? (
      <div>
        <h2>security panel</h2>
        <button type="button" onClick={() => openStepUpFor(mocks.action)}>
          open step up
        </button>
        <button
          type="button"
          onClick={() => openStepUpFor(undefined as unknown as () => Promise<void>)}
        >
          open empty step up
        </button>
      </div>
    ) : null,
}))

import Settings from "@/pages/Settings"

describe("Settings container closure", () => {
  beforeEach(() => {
    mocks.initialSearch = { tab: 0, spotify: undefined }
    mocks.navigate.mockReset()
    mocks.navigate.mockImplementation(
      (args: { search?: (previous: Record<string, unknown>) => unknown }) => {
        if (args.search && mocks.setSearch) {
          mocks.setSearch(args.search)
        }
      }
    )
    mocks.setSearch = null
    mocks.action.mockClear()
  })

  it("renders the default tab, navigates to profile and covers both tab URL branches", async () => {
    const user = userEvent.setup()
    render(<Settings />)

    expect(screen.getByRole("heading", { name: "settings:page.title" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "general panel" })).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "settings:tabs.account" }))
    expect(await screen.findByRole("heading", { name: "profile panel" })).toBeInTheDocument()
    expect(mocks.navigate).toHaveBeenCalled()
    const profileNavigation = mocks.navigate.mock.calls.at(-1)?.[0] as {
      search: (previous: Record<string, unknown>) => Record<string, unknown>
    }
    expect(profileNavigation.search({ tab: 0, spotify: "connected" })).toEqual({
      tab: 1,
      spotify: "connected",
    })

    await user.click(screen.getByRole("tab", { name: "settings:tabs.integrations" }))
    expect(await screen.findByRole("heading", { name: "integrations panel" })).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "settings:tabs.general" }))
    const generalNavigation = mocks.navigate.mock.calls.at(-1)?.[0] as {
      search: (previous: Record<string, unknown>) => Record<string, unknown>
    }
    expect(generalNavigation.search({ tab: 1 })).toEqual({})
  })

  it("handles Spotify callback statuses and removes the query parameter", async () => {
    const { rerender } = render(<Settings />)
    mocks.setSearch?.(() => ({ tab: 0, spotify: "connected" }))

    await waitFor(() =>
      expect(
        screen.getByText("settings:integrations.spotify.snackbar.connected")
      ).toBeInTheDocument()
    )
    expect(screen.getByText("settings:integrations.spotify.snackbar.connected")).toHaveClass(
      "bg-success-bg"
    )
    expect(mocks.navigate).toHaveBeenCalled()

    mocks.setSearch?.(() => ({ tab: 0, spotify: "error" }))
    await waitFor(() =>
      expect(
        screen.getByText("settings:integrations.spotify.snackbar.connectFailed")
      ).toBeInTheDocument()
    )
    expect(screen.getByText("settings:integrations.spotify.snackbar.connectFailed")).toHaveClass(
      "bg-error-bg"
    )

    rerender(<Settings />)
    await userEvent.setup().click(screen.getByRole("button", { name: "dismiss snackbar" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("runs step-up actions, closes the dialog, and handles an empty callback", async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole("tab", { name: "settings:tabs.security" }))

    await user.click(await screen.findByRole("button", { name: "open step up" }))
    expect(screen.getByRole("dialog", { name: "step up" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "complete step up" }))
    await waitFor(() => expect(mocks.action).toHaveBeenCalledOnce())
    expect(screen.queryByRole("dialog", { name: "step up" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "open empty step up" }))
    await user.click(screen.getByRole("button", { name: "close step up" }))
    expect(screen.queryByRole("dialog", { name: "step up" })).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "settings:tabs.general" }))
    await user.click(screen.getByRole("button", { name: "show info snackbar" }))
    expect(screen.getByText("info message")).toHaveClass("bg-surface-raised")
    await user.click(screen.getByRole("button", { name: "dismiss snackbar" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
