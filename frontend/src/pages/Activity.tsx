import { useTranslation } from "react-i18next"
import "@/styles/tokens/activity.css"
import { PageLayout } from "@/components/layout/PageLayout"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { ActivityFeature } from "@/features/activity"

/**
 * Activity page — Wave 112 SW2 thin wrapper.
 *
 * Mirror of `pages/Events.tsx` and `pages/News.tsx`: the page owns SEO + the
 * <PageLayout> chrome, the feature owns content + state. FeatureErrorBoundary
 * isolates a renderer crash from the global navbar.
 */
export default function Activity() {
  const { t } = useTranslation(["activity"])

  return (
    <PageLayout
      variant="full"
      seo={{
        title: t("activity:title"),
        description: t("activity:pageDescription"),
      }}
    >
      <FeatureErrorBoundary featureName="activity">
        <ActivityFeature />
      </FeatureErrorBoundary>
    </PageLayout>
  )
}
