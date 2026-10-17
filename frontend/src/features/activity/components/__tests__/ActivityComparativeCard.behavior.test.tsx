import { render, screen } from "@testing-library/react"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"

import { ActivityComparativeCard } from "@/features/activity/components/ActivityComparativeCard"
import enActivity from "@/i18n/locales/en/activity.json"
import ruActivity from "@/i18n/locales/ru/activity.json"

async function renderComparison(language: string, current: number, delta: number) {
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    resources: { en: { activity: enActivity }, ru: { activity: ruActivity } },
    interpolation: { escapeValue: false },
  })
  return render(
    <I18nextProvider i18n={i18n}>
      <ActivityComparativeCard
        label="Events"
        current={current}
        previous={10}
        delta={delta}
        colorVar="rgb(12, 34, 56)"
      />
    </I18nextProvider>
  )
}

describe("Activity comparison presentation", () => {
  it.each([
    { direction: "positive", current: 12, delta: 20, expected: "+20.0%" },
    { direction: "negative", current: 8, delta: -20, expected: "-20.0%" },
  ])(
    "renders one decorative indicator for a $direction change",
    async ({ current, delta, expected }) => {
      const { container } = await renderComparison("en", current, delta)

      expect(screen.getByText(String(current))).toBeVisible()
      expect(screen.getByText("vs 10")).toBeVisible()
      expect(screen.getByText(expected)).toBeVisible()
      const indicators = container.querySelectorAll("svg")
      expect(indicators).toHaveLength(1)
      expect(indicators[0]).toHaveAttribute("aria-hidden", "true")
    }
  )

  it.each([
    ["en", enActivity.comparative.unchanged, "vs 10"],
    [
      "ru",
      ruActivity.comparative.unchanged,
      ruActivity.comparative.vsPrevious.replace("{{value}}", "10"),
    ],
  ])("localizes an unchanged comparison in %s", async (language, unchanged, previous) => {
    const { container } = await renderComparison(language, 10, 0)

    expect(screen.getByText("10")).toBeVisible()
    expect(screen.getByText(previous)).toBeVisible()
    expect(screen.getByText(unchanged)).toBeVisible()
    expect(screen.queryByText(/[+-]0\.0%/)).not.toBeInTheDocument()
    const indicators = container.querySelectorAll("svg")
    expect(indicators).toHaveLength(1)
    expect(indicators[0]).toHaveAttribute("aria-hidden", "true")
  })

  it("uses the configured metric color for its current value", async () => {
    await renderComparison("en", 12, 20)

    expect(screen.getByText("12")).toHaveStyle({ color: "rgb(12, 34, 56)" })
  })

  it.each([
    {
      direction: "positive",
      current: 12,
      delta: 20,
      label: "+20.0%",
      token: "text-[var(--activity-positive-accent)]",
    },
    {
      direction: "negative",
      current: 8,
      delta: -20,
      label: "-20.0%",
      token: "text-[var(--activity-negative-accent)]",
    },
    {
      direction: "neutral",
      current: 10,
      delta: 0,
      label: enActivity.comparative.unchanged,
      token: "text-text-tertiary",
    },
  ])("selects only the $direction trend color", async ({ current, delta, label, token }) => {
    await renderComparison("en", current, delta)
    const trend = screen.getByText(label)

    expect(trend).toBeVisible()
    expect(trend).toHaveClass(token)
    for (const competingToken of [
      "text-[var(--activity-positive-accent)]",
      "text-[var(--activity-negative-accent)]",
      "text-text-tertiary",
    ]) {
      if (competingToken !== token) expect(trend).not.toHaveClass(competingToken)
    }
  })
})
