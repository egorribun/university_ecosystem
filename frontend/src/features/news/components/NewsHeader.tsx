import { Newspaper as ArticleIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import FadeSection from "@/components/FadeSection"
import { Button } from "@/components/ui"

interface NewsHeaderProps {
  onAddClick: () => void
  isAdmin: boolean
}

export const NewsHeader = ({ onAddClick, isAdmin }: NewsHeaderProps) => {
  const { t } = useTranslation(["news"])

  return (
    <header>
      <FadeSection delay="80ms" className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-medium) border border-glass-border text-brand shadow-glass transition-transform duration-fast hover:scale-105 backdrop-blur-md">
          <ArticleIcon className="h-7 w-7" />
        </div>
        <h1 className="text-(--fs-page-title) font-bold tracking-tight">{t("news:pageTitle")}</h1>
      </FadeSection>

      {isAdmin && (
        <FadeSection delay="140ms" className="mb-6 flex justify-start">
          <Button id="news-header-add-btn" size="lg" onClick={onAddClick} className="px-6 text-fluid-title-sm">
            {t("news:actions.add")}
          </Button>
        </FadeSection>
      )}
    </header>
  )
}
