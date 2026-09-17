import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "../table"

describe("table primitive style contracts", () => {
  it("preserves the semantic elements and baseline layout classes", () => {
    const { container } = render(
      <Table>
        <TableCaption>Caption</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Heading</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Cell</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Footer</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    )

    expect(container.querySelector("div")).toHaveClass("relative", "w-full", "overflow-auto")
    expect(container.querySelector("table")).toHaveClass("w-full", "caption-bottom", "text-sm")
    expect(container.querySelector("thead")).toHaveClass("[&_tr]:border-b")
    expect(container.querySelector("tbody")).toHaveClass("[&_tr:last-child]:border-0")
    expect(container.querySelector("tfoot")).toHaveClass(
      "border-t",
      "bg-surface/50",
      "font-medium",
      "[&>tr]:last:border-b-0"
    )
    expect(container.querySelector("tbody tr")).toHaveClass(
      "border-b",
      "transition-colors",
      "hover:bg-surface-hover/50",
      "data-[state=selected]:bg-surface-selected"
    )
    expect(container.querySelector("th")).toHaveClass(
      "h-10",
      "px-2",
      "text-left",
      "align-middle",
      "font-medium",
      "text-text-secondary",
      "[&:has([role=checkbox])]:pr-0"
    )
    expect(container.querySelector("td")).toHaveClass(
      "p-2",
      "align-middle",
      "[&:has([role=checkbox])]:pr-0"
    )
    expect(container.querySelector("caption")).toHaveClass("mt-4", "text-sm", "text-text-tertiary")
  })
})
