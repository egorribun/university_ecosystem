import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { FeatureFlag } from "@/types/Admin"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const state = vi.hoisted(() => ({
  reducedMotion: false,
  query: { data: [] as FeatureFlag[], isPending: false },
  queryClient: { setQueryData: vi.fn() },
  patch: vi.fn().mockResolvedValue({}),
  updateCache: vi.fn(),
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

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => state.queryClient,
}))

vi.mock("@/api/client", () => ({
  default: { patch: state.patch },
}))

vi.mock("@/api/hooks/adminFeatureFlags", () => ({
  useAdminFeatureFlagsQuery: () => state.query,
  updateFeatureFlagInCache: state.updateCache,
}))

vi.mock("@/components/settings", () => ({
  Chip: ({ label }: { label: string }) => <span data-testid={`chip-${label}`}>{label}</span>,
  SwitchControl: ({ checked, onChange }: { checked: boolean; onChange: () => void }) => (
    <button type="button" aria-label={`toggle-${checked ? "on" : "off"}`} onClick={onChange}>
      {String(checked)}
    </button>
  ),
}))

vi.mock("lucide-react", () => ({
  Info: () => <span aria-hidden="true" />,
  Percent: () => <span aria-hidden="true" />,
}))

import { AdminFeatureFlagsFeature } from "@/features/admin/AdminFeatureFlagsFeature"

const flags: FeatureFlag[] = [
  {
    name: "always-on",
    status: "enabled",
    description: "Enabled flag",
    percentage: 100,
    allowed_users: [],
    allowed_groups: [],
    metadata: { source: "test" },
  },
  {
    name: "off-by-default",
    status: "disabled",
    description: "Disabled flag",
    percentage: 0,
    allowed_users: [],
    allowed_groups: [],
    metadata: {},
  },
  {
    name: "gradual-rollout",
    status: "percentage",
    description: "Percentage flag",
    percentage: 35,
    allowed_users: [],
    allowed_groups: [],
    metadata: { cohort: "beta" },
  },
  {
    // Defensive runtime payloads can contain a value outside the declared union.
    ...({
      name: "unknown-status",
      status: "unexpected",
      description: "Unknown status",
      percentage: 0,
      allowed_users: [],
      allowed_groups: [],
      metadata: {},
    } as unknown as FeatureFlag),
  },
]

beforeEach(() => {
  state.reducedMotion = false
  state.query = { data: [], isPending: false }
  state.patch.mockReset().mockResolvedValue({})
  state.updateCache.mockReset()
  state.queryClient.setQueryData.mockReset()
})

describe("AdminFeatureFlagsFeature closure", () => {
  it("renders the query loading state", () => {
    state.query = { data: [], isPending: true }

    render(<AdminFeatureFlagsFeature />)

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("covers status rendering, toggle mutations, percentage updates, and reduced motion", async () => {
    state.query = { data: flags, isPending: false }
    state.reducedMotion = true

    const { rerender } = render(<AdminFeatureFlagsFeature />)

    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getByTestId("chip-ENABLED")).toBeInTheDocument()
    expect(screen.getByTestId("chip-DISABLED")).toBeInTheDocument()
    expect(screen.getByTestId("chip-PERCENTAGE")).toBeInTheDocument()
    expect(screen.getByTestId("chip-UNEXPECTED")).toBeInTheDocument()
    expect(screen.getByDisplayValue("35")).toBeInTheDocument()
    expect(screen.getAllByText("featureFlags.rollout.global")).toHaveLength(3)

    const toggles = screen.getAllByRole("button", { name: /toggle-/ })
    fireEvent.click(toggles[0]!)
    await waitFor(() =>
      expect(state.patch).toHaveBeenCalledWith("/admin/feature-flags/always-on", {
        status: "disabled",
      })
    )
    expect(state.updateCache).toHaveBeenCalledWith(state.queryClient, "always-on", {
      status: "disabled",
    })

    fireEvent.click(toggles[1]!)
    await waitFor(() =>
      expect(state.patch).toHaveBeenCalledWith("/admin/feature-flags/off-by-default", {
        status: "enabled",
      })
    )

    fireEvent.change(screen.getByDisplayValue("35"), { target: { value: "60" } })
    await waitFor(() =>
      expect(state.patch).toHaveBeenCalledWith("/admin/feature-flags/gradual-rollout", {
        status: "percentage",
        percentage: 60,
      })
    )
    expect(state.updateCache).toHaveBeenCalledWith(state.queryClient, "gradual-rollout", {
      status: "percentage",
      percentage: 60,
    })

    state.reducedMotion = false
    rerender(<AdminFeatureFlagsFeature />)
    expect(screen.getByRole("table")).toBeInTheDocument()
  })
})
