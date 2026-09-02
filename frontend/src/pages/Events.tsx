import { PageLayout } from "@/components/layout/PageLayout"
import { useTranslation } from "react-i18next"
import "@/styles/tokens/events.css"
import { EventsFeature } from "@/features/events"

const Events = () => {
  const { t } = useTranslation(["events"])

  return (
    <PageLayout
      variant="full"
      seo={{
        title: t("events:pageTitle"),
        description: t("events:pageDescription"),
      }}
    >
      <EventsFeature />
    </PageLayout>
  )
}

export default Events
