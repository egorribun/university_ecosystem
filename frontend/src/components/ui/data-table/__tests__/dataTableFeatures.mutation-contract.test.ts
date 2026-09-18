import { describe, expect, it } from "vitest"

import {
  columnFacetingFeature,
  columnFilteringFeature,
  columnVisibilityFeature,
  filterFn_arrIncludes,
  filterFn_equals,
  filterFn_inDateRange,
  filterFn_inNumberRange,
  filterFn_includesString,
  filterFn_weakEquals,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_datetime,
  sortFn_text,
} from "@tanstack/react-table"

import { dataTableFeatures } from "@/components/ui/data-table/dataTableFeatures"

describe("dataTableFeatures mutation contracts", () => {
  it("retains every table feature and row-model factory", () => {
    expect(dataTableFeatures.columnFilteringFeature).toBe(columnFilteringFeature)
    expect(dataTableFeatures.filteredRowModel).toBeTypeOf("function")
    expect(dataTableFeatures.columnFacetingFeature).toBe(columnFacetingFeature)
    expect(dataTableFeatures.facetedRowModel).toBeTypeOf("function")
    expect(dataTableFeatures.facetedUniqueValues).toBeTypeOf("function")
    expect(dataTableFeatures.columnVisibilityFeature).toBe(columnVisibilityFeature)
    expect(dataTableFeatures.rowPaginationFeature).toBe(rowPaginationFeature)
    expect(dataTableFeatures.paginatedRowModel).toBeTypeOf("function")
    expect(dataTableFeatures.rowSelectionFeature).toBe(rowSelectionFeature)
    expect(dataTableFeatures.rowSortingFeature).toBe(rowSortingFeature)
    expect(dataTableFeatures.sortedRowModel).toBeTypeOf("function")
  })

  it("retains the complete named filter and sort function registries", () => {
    expect(dataTableFeatures.filterFns).toEqual({
      arrIncludes: filterFn_arrIncludes,
      equals: filterFn_equals,
      inDateRange: filterFn_inDateRange,
      inNumberRange: filterFn_inNumberRange,
      includesString: filterFn_includesString,
      weakEquals: filterFn_weakEquals,
    })
    expect(dataTableFeatures.sortFns).toEqual({
      alphanumeric: sortFn_alphanumeric,
      datetime: sortFn_datetime,
      text: sortFn_text,
    })
  })
})
