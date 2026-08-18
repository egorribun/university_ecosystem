import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { FeatureFlag } from "@/types/Admin"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const state = vi.hoisted(() => ({
  reducedMotion: false,
  query: { data: [] as FeatureFlag[], isPending: false },
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => state.reducedMotion,
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
  Chip: ({ label }: { label: string }) => <span data-testid={`chip-${label}`}>{label}</span>,
}))

vi.mock("lucide-react", () => ({
  Info: () => <span aria-hidden="true" />,
}))

import { AdminFeatureFlagsFeature } from "@/features/admin/AdminFeatureFlagsFeature"

const flags: FeatureFlag[] = [
  {
    name: "always-on",
    enabled: true,
    default: true,
    description: "Enabled flag",
    provider: "flagd Provider",
    evaluation_reason: "TARGETING_MATCH",
    management: "gitops",
    config_path: "k8s/flagd/flags.json",
  },
  {
    name: "off-by-default",
    enabled: false,
    default: false,
    description: "Disabled flag",
    provider: "flagd Provider",
    evaluation_reason: "DEFAULT",
    management: "gitops",
    config_path: "k8s/flagd/flags.json",
  },
]

beforeEach(() => {
  state.reducedMotion = false
  state.query = { data: [], isPending: false }
})

describe("AdminFeatureFlagsFeature closure", () => {
  it("renders the query loading state", () => {
    state.query = { data: [], isPending: true }

    render(<AdminFeatureFlagsFeature />)

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("renders effective values and the read-only GitOps ownership contract", () => {
    state.query = { data: flags, isPending: false }
    state.reducedMotion = true

    const { rerender } = render(<AdminFeatureFlagsFeature />)

    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByTestId("chip-featureFlags.values.on")).toBeInTheDocument()
    expect(screen.getByTestId("chip-featureFlags.values.off")).toBeInTheDocument()
    expect(screen.getByText("featureFlags.management.notice")).toBeInTheDocument()
    expect(screen.getAllByText("k8s/flagd/flags.json")).toHaveLength(2)
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    expect(screen.queryByRole("slider")).not.toBeInTheDocument()

    state.reducedMotion = false
    rerender(<AdminFeatureFlagsFeature />)
    expect(screen.getByRole("table")).toBeInTheDocument()
  })
})
