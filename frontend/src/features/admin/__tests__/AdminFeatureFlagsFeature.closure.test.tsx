import { render, screen, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { FeatureFlag } from "@/types/Admin"

const state = vi.hoisted(() => ({
  query: { data: [] as FeatureFlag[] | undefined, isPending: false },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { value?: number }) =>
      values ? `${key}:${values.value ?? ""}` : key,
  }),
}))

vi.mock("@/api/hooks/adminFeatureFlags", () => ({
  useAdminFeatureFlagsQuery: () => state.query,
}))

vi.mock("@/components/settings", () => ({
  Chip: ({ label, color }: { label: string; color: string }) => (
    <span data-testid="effective-chip" data-color={color}>
      {label}
    </span>
  ),
}))

vi.mock("lucide-react", () => ({
  Flag: () => <span data-testid="empty-flag-icon" aria-hidden="true" />,
  Info: () => <span aria-hidden="true" />,
}))

import { AdminFeatureFlagsFeature } from "@/features/admin/AdminFeatureFlagsFeature"

const flags: FeatureFlag[] = [
  {
    name: "enabled-by-targeting",
    enabled: true,
    default: false,
    description: "Enabled flag",
    provider: "flagd Provider",
    evaluation_reason: "TARGETING_MATCH",
    management: "gitops",
    config_path: "k8s/flagd/flags.json",
  },
  {
    name: "disabled-by-default",
    enabled: false,
    default: true,
    description: "Disabled flag",
    provider: "flagd Provider",
    evaluation_reason: "DEFAULT",
    management: "gitops",
    config_path: "k8s/flagd/flags.json",
  },
]

function row(name: string) {
  const tableRow = screen.getByText(name).closest("tr")
  if (!tableRow) throw new Error(`row ${name} not rendered`)
  return within(tableRow)
}

beforeEach(() => {
  state.query = { data: [], isPending: false }
})

describe("AdminFeatureFlagsFeature closure", () => {
  it("renders the query loading state", () => {
    state.query = { data: [], isPending: true }

    render(<AdminFeatureFlagsFeature />)

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("explains an empty registry instead of rendering an empty table", () => {
    render(<AdminFeatureFlagsFeature />)

    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(
      screen.getByRole("heading", { level: 2, name: "featureFlags.empty.title" })
    ).toBeInTheDocument()
    expect(screen.getByText("featureFlags.empty.description")).toBeInTheDocument()
    expect(screen.getByTestId("empty-flag-icon")).toBeInTheDocument()
    expect(screen.getByText("featureFlags.management.notice")).toBeInTheDocument()
  })

  it("treats a settled query without data as an empty registry", () => {
    state.query = { data: undefined, isPending: false }

    render(<AdminFeatureFlagsFeature />)

    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.getByText("featureFlags.empty.title")).toBeInTheDocument()
  })

  it("renders the page heading and subtitle", () => {
    render(<AdminFeatureFlagsFeature />)

    expect(
      screen.getByRole("heading", { level: 1, name: "featureFlags.title" })
    ).toBeInTheDocument()
    expect(screen.getByText("featureFlags.subtitle")).toBeInTheDocument()
  })

  it("renders effective values, fallbacks and the read-only GitOps ownership contract", () => {
    state.query = { data: flags, isPending: false }

    render(<AdminFeatureFlagsFeature />)

    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.queryByText("featureFlags.empty.title")).not.toBeInTheDocument()

    const enabled = row("enabled-by-targeting")
    expect(enabled.getByTestId("effective-chip")).toHaveTextContent("featureFlags.values.on")
    expect(enabled.getByTestId("effective-chip")).toHaveAttribute("data-color", "success")
    expect(enabled.getAllByText("featureFlags.values.off")).toHaveLength(1)
    expect(enabled.getByText("TARGETING_MATCH")).toBeInTheDocument()

    const disabled = row("disabled-by-default")
    expect(disabled.getByTestId("effective-chip")).toHaveTextContent("featureFlags.values.off")
    expect(disabled.getByTestId("effective-chip")).toHaveAttribute("data-color", "default")
    expect(disabled.getAllByText("featureFlags.values.on")).toHaveLength(1)
    expect(disabled.getByText("DEFAULT")).toBeInTheDocument()

    expect(screen.getByText("featureFlags.management.notice")).toBeInTheDocument()
    expect(screen.getAllByText("k8s/flagd/flags.json")).toHaveLength(2)
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    expect(screen.queryByRole("slider")).not.toBeInTheDocument()
  })
})
