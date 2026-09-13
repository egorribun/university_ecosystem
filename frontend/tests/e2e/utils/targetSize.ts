import { expect, type Locator } from "@playwright/test"

type TargetGeometry = {
  height: number
  paddingBottom: number
  paddingLeft: number
  paddingRight: number
  paddingTop: number
  width: number
}

async function readTargetGeometry(locator: Locator, label: string): Promise<TargetGeometry> {
  await expect(locator, `${label}: locator must resolve to exactly one target`).toHaveCount(1)
  await expect(locator, `${label}: target must be visible`).toBeVisible()
  await expect(locator, `${label}: target must be enabled`).toBeEnabled()

  return locator.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const style = getComputedStyle(element)
    return {
      height: rect.height,
      paddingBottom: Number.parseFloat(style.paddingBottom),
      paddingLeft: Number.parseFloat(style.paddingLeft),
      paddingRight: Number.parseFloat(style.paddingRight),
      paddingTop: Number.parseFloat(style.paddingTop),
      width: rect.width,
    }
  })
}

export async function assertControlTarget(locator: Locator, label: string): Promise<void> {
  let geometry = await readTargetGeometry(locator, label)

  try {
    await expect
      .poll(
        async () => {
          geometry = await readTargetGeometry(locator, label)
          return {
            height: geometry.height >= 44,
            width: geometry.width >= 44,
          }
        },
        { message: `${label}: expected both target axes to reach at least 44 CSS px` }
      )
      .toEqual({ height: true, width: true })
  } catch (error) {
    expect(
      geometry.width,
      `${label}: expected width >= 44 CSS px, observed ${geometry.width.toFixed(2)} CSS px`
    ).toBeGreaterThanOrEqual(44)
    expect(
      geometry.height,
      `${label}: expected height >= 44 CSS px, observed ${geometry.height.toFixed(2)} CSS px`
    ).toBeGreaterThanOrEqual(44)
    throw error
  }

  geometry = await readTargetGeometry(locator, label)

  expect(
    geometry.width,
    `${label}: expected width >= 44 CSS px, observed ${geometry.width.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(44)
  expect(
    geometry.height,
    `${label}: expected height >= 44 CSS px, observed ${geometry.height.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(44)
}

export async function assertTextLinkTarget(locator: Locator, label: string): Promise<void> {
  const geometry = await readTargetGeometry(locator, label)

  expect(
    geometry.height,
    `${label}: expected height >= 24 CSS px, observed ${geometry.height.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(24)
  expect(
    geometry.paddingLeft,
    `${label}: expected left padding >= 8 CSS px, observed ${geometry.paddingLeft.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(8)
  expect(
    geometry.paddingRight,
    `${label}: expected right padding >= 8 CSS px, observed ${geometry.paddingRight.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(8)
  expect(
    geometry.paddingTop,
    `${label}: expected top padding >= 6 CSS px, observed ${geometry.paddingTop.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(6)
  expect(
    geometry.paddingBottom,
    `${label}: expected bottom padding >= 6 CSS px, observed ${geometry.paddingBottom.toFixed(2)} CSS px`
  ).toBeGreaterThanOrEqual(6)
}
