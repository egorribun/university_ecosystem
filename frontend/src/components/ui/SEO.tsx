import {
  createContext,
  useCallback,
  useContext,
  useId,
  useLayoutEffect,
  useMemo,
  useState,
  type FC,
  type ReactNode,
} from "react"
import { useTranslation } from "react-i18next"
import {
  registerSeoReadinessInstance,
  unregisterSeoReadinessInstance,
} from "./seoReadinessRegistry"

interface SeoReadinessContextValue {
  hasPageSeo: boolean
  register: (instanceId: string) => void
  unregister: (instanceId: string) => void
}

const noop = () => undefined
const SeoReadinessContext = createContext<SeoReadinessContextValue>({
  hasPageSeo: false,
  register: noop,
  unregister: noop,
})

export function SeoReadinessProvider({ children }: { children: ReactNode }) {
  const [instances, setInstances] = useState<ReadonlySet<string>>(() => new Set())
  const register = useCallback((instanceId: string) => {
    setInstances((current) => registerSeoReadinessInstance(current, instanceId))
  }, [])
  const unregister = useCallback((instanceId: string) => {
    setInstances((current) => unregisterSeoReadinessInstance(current, instanceId))
  }, [])
  const value = useMemo(
    () => ({ hasPageSeo: instances.size > 0, register, unregister }),
    [instances, register, unregister]
  )

  return <SeoReadinessContext.Provider value={value}>{children}</SeoReadinessContext.Provider>
}

export function usePageSeoReady(): boolean {
  return useContext(SeoReadinessContext).hasPageSeo
}

export interface SEOProps {
  title: string
  description?: string
  image?: string
  type?: string
}

export const SEO: FC<SEOProps> = ({ title, description, image, type = "website" }) => {
  const { t } = useTranslation(["navigation"])
  const { register, unregister } = useContext(SeoReadinessContext)
  const instanceId = useId()
  useLayoutEffect(() => {
    register(instanceId)
    return () => unregister(instanceId)
  }, [instanceId, register, unregister])

  const siteTitle = "University Ecosystem"
  const fullTitle = `${title} | ${siteTitle}`
  const resolvedDescription = description?.trim() || t("brandDescription")
  const resolvedSocialDescription = description?.trim() || t("socialDescription")
  const resolvedImage = image?.trim() || "/icon-512.png"

  return (
    <>
      <title>{fullTitle}</title>
      <meta name="title" content={fullTitle} />
      <meta name="description" content={resolvedDescription} />
      <meta property="og:type" content={type} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={resolvedSocialDescription} />
      <meta property="og:image" content={resolvedImage} />
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={resolvedSocialDescription} />
      <meta name="twitter:image" content={resolvedImage} />
    </>
  )
}
