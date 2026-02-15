import { useTranslation } from "react-i18next"
import Layout from "./Layout"
import { Skeleton } from "@/components/ui"

type LoadingStateProps = {
  label?: string
}

export default function LoadingState({ label }: LoadingStateProps) {
  const { t } = useTranslation("common")
  const loadingLabel = label ?? t("statuses.loading")

  return (
    <Layout>
      <header className="px-4 sm:px-8 py-6 sm:py-8 border-b border-glass-border/(--opacity-subtle)">
        <h1 className="sr-only">{loadingLabel}</h1>
        <Skeleton
          className="w-[62%] sm:w-[44%] max-w-(--w-label-lg) h-8 sm:h-9 rounded-xl"
          aria-hidden="true"
        />
      </header>

      <section
        role="status"
        aria-live="polite"
        aria-busy="true"
        className="flex flex-col items-center justify-center gap-6 px-4 py-20 md:py-24 min-h-60dvh text-center"
      >
        <div className="relative">
          <div className="h-12 w-12 rounded-full border-4 border-brand/(--opacity-subtle) border-t-brand animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-2 w-2 rounded-full bg-brand animate-pulse" />
          </div>
        </div>

        <p className="text-base font-bold tracking-tight text-(--text-secondary) animate-pulse">
          {loadingLabel}
        </p>
      </section>
    </Layout>
  )
}
