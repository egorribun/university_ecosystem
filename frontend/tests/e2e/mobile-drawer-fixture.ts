import { test as base } from "@playwright/test"
import {
  attachDrawerPhaseOnFailure,
  createDrawerPhaseTracker,
  type DrawerPhaseTracker,
} from "../e2e-live/mobile-drawer-rapid"

export { verifyRapidDrawerNavigation } from "../e2e-live/mobile-drawer-rapid"

export const test = base.extend<{ drawerPhase: DrawerPhaseTracker }>({
  drawerPhase: [
    async ({ browserName }, provide, testInfo) => {
      const phase = createDrawerPhaseTracker(browserName)
      try {
        await provide(phase)
      } finally {
        await attachDrawerPhaseOnFailure(testInfo, phase)
      }
    },
    { auto: true },
  ],
})
