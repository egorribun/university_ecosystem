import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { MapCategoryFilter } from "@/components/map/MapCategoryFilter"

describe("MapCategoryFilter", () => {
  it("reports the selected category", async () => {
    const onChange = vi.fn()
    render(<MapCategoryFilter active="all" onChange={onChange} />)

    await userEvent.click(screen.getAllByRole("radio")[1]!)

    expect(onChange).toHaveBeenCalledOnce()
    expect(onChange).not.toHaveBeenCalledWith("all")
  })
})
