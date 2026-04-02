import { useTranslation } from "react-i18next"
import { SEO } from "@/components/ui/SEO"
import { NewsFeature } from "@/features/news"

const News = () => {
  const { t } = useTranslation(["news"])

  return (
    <>
      <SEO
        title={t("news:pageTitle")}
        description={t("news:pageDescription", {
          defaultValue: "Latest news and updates from the university ecosystem.",
        })}
      />
      <NewsFeature />
    </>
  )
}

export default News
