import "@/styles/tokens/messenger.css"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { MessengerFeature } from "@/features/messenger"

/**
 * Messenger page — Wave 145 SW2 thin wrapper.
 *
 * Mirror of `pages/Activity.tsx` (W112 SW2 reference implementation): the page
 * owns FeatureErrorBoundary chrome; the feature (`features/messenger/MessengerFeature`)
 * owns content + state. Does NOT use `<PageLayout>` because chat fills viewport
 * (h-full + overflow-hidden + mobile safe-area paddingBottom semantics inside
 * MessengerFeature) — incompatible with PageLayout's scrolling/max-width variants.
 *
 * Routes `messenger.tsx` (list) + `messenger.$chatId.tsx` (detail) both
 * lazy-import this file; `useMessengerController` reads `chatId` from URL
 * params so the same component renders for both routes.
 */
export default function Messenger() {
  return (
    <FeatureErrorBoundary featureName="messenger">
      <MessengerFeature />
    </FeatureErrorBoundary>
  )
}
