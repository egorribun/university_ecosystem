import { useTranslation } from "react-i18next"
import "@/styles/tokens/news.css"
import { SEO } from "@/components/ui/SEO"
import { NewsFeature } from "@/features/news"
import Layout from "@/components/Layout"

const News = () => {
  const { t } = useTranslation(["news"])

  return (
    <Layout>
      <SEO title={t("news:pageTitle")} description={t("news:pageDescription")} />
      <NewsFeature />
    </Layout>
  )
}

export default News
