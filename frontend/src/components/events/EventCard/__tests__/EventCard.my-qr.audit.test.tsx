import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const useLogic = vi.hoisted(() =>
  vi.fn((_props: unknown) => ({
    timeStatus: { status: "soon" },
    registration: { participantCount: 1, isRegistered: true, isLoading: false },
  }))
)

vi.mock("@/hooks/useEventCardLogic", () => ({ useEventCardLogic: useLogic }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("../EventCardView", () => ({ EventCardView: () => <div data-testid="event-card-view" /> }))
vi.mock("../EventCardSkeleton", () => ({ EventCardSkeleton: () => <div /> }))

import EventCard from "../EventCard"

describe("AUD-260 event-card memo inputs", () => {
  it("forwards a changed token, refresh callback and My storage mode to the logic", async () => {
    const firstChange = vi.fn()
    const secondChange = vi.fn()
    const { rerender } = render(
      <EventCard id="event-1" my_qr_token="first" onChange={firstChange} />
    )
    await screen.findByTestId("event-card-view")
    useLogic.mockClear()

    rerender(<EventCard id="event-1" my_qr_token="second" onChange={firstChange} />)
    await waitFor(() => expect(useLogic).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    expect(useLogic.mock.calls.at(-1)?.[0]).toMatchObject({ my_qr_token: "second" })

    rerender(<EventCard id="event-1" my_qr_token="second" onChange={secondChange} />)
    await waitFor(() => expect(useLogic).toHaveBeenCalledTimes(2), { timeout: 1_000 })
    expect(useLogic.mock.calls.at(-1)?.[0]).toMatchObject({ onChange: secondChange })

    rerender(
      <EventCard id="event-1" my_qr_token="second" onChange={secondChange} qrStorage="memory" />
    )
    await waitFor(() => expect(useLogic).toHaveBeenCalledTimes(3), { timeout: 1_000 })
    expect(useLogic.mock.calls.at(-1)?.[0]).toMatchObject({ qrStorage: "memory" })
  })
})
