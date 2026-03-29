import { useTranslation } from "react-i18next"
import Layout from "@/components/Layout"
import { SEO } from "@/components/ui/SEO"
import PageFadeIn from "@/components/motion/PageFadeIn"
import { NewsFeature } from "@/features/news"

const News = () => {
  const { t } = useTranslation(["news"])

  return (
    <Layout>
      <SEO
        title={t("news:pageTitle")}
        description={t("news:pageDescription", {
          defaultValue: "Latest news and updates from the university ecosystem.",
        })}
      />
      <PageFadeIn>
        <NewsFeature />
      </PageFadeIn>
    </Layout>
  )
}

export default News
