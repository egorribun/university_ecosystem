import { describe, expect, it, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { SpotifySection } from "../sections/SpotifySection"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/components/settings", () => ({
  SectionTitle: ({ children }: any) => <h2>{children}</h2>,
  Chip: ({ label }: any) => <span>{label}</span>,
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}))

describe("SpotifySection component", () => {
  it("renders disconnected state", () => {
    const onConnect = vi.fn()
    const onDisconnect = vi.fn()

    render(
      <SpotifySection
        connected={false}
        displayName=""
        onConnect={onConnect}
        onDisconnect={onDisconnect}
        setSnackbar={vi.fn()}
      />
    )

    expect(
      screen.getByText("settings:integrations.spotify.status.disconnected")
    ).toBeInTheDocument()
    expect(
      screen.queryByText("settings:integrations.spotify.status.connected")
    ).not.toBeInTheDocument()

    const connectBtn = screen.getByText("settings:integrations.spotify.connect")
    fireEvent.click(connectBtn)
    expect(onConnect).toHaveBeenCalled()
  })

  it("renders connected state with display name", () => {
    const onConnect = vi.fn()
    const onDisconnect = vi.fn()

    render(
      <SpotifySection
        connected={true}
        displayName="SpotifyUser123"
        onConnect={onConnect}
        onDisconnect={onDisconnect}
        setSnackbar={vi.fn()}
      />
    )

    expect(screen.getByText("settings:integrations.spotify.status.connected")).toBeInTheDocument()
    expect(screen.getByText("SpotifyUser123")).toBeInTheDocument()

    const disconnectBtn = screen.getByText("settings:integrations.spotify.disconnect")
    fireEvent.click(disconnectBtn)
    expect(onDisconnect).toHaveBeenCalled()
  })
})
