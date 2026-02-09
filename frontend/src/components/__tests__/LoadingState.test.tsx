import { screen } from "@testing-library/react"
import LoadingState from "@/components/LoadingState"
import { renderWithA11y } from "@/tests/axeTest"

describe("LoadingState", () => {
  test("renders an accessible busy status with page landmarks", async () => {
    const { container } = await renderWithA11y(<LoadingState />)

    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(screen.getAllByText(/loading/i)[0]).toBeInTheDocument()
    expect(container.querySelector("main#main")).not.toBeNull()
    expect(container.querySelector("header")).not.toBeNull()
  })
})




