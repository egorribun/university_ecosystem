import type { FC } from "react"

interface SEOProps {
  title: string
  description?: string
  image?: string
  type?: string
}

export const SEO: FC<SEOProps> = ({ title, description, image, type = "website" }) => {
  const siteTitle = "University Ecosystem"
  const fullTitle = `${title} | ${siteTitle}`

  return (
    <>
      <title>{fullTitle}</title>
      <meta name="title" content={fullTitle} />
      {description && <meta name="description" content={description} />}
      <meta property="og:type" content={type} />
      <meta property="og:title" content={fullTitle} />
      {description && <meta property="og:description" content={description} />}
      {image && <meta property="og:image" content={image} />}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      {description && <meta name="twitter:description" content={description} />}
      {image && <meta name="twitter:image" content={image} />}
    </>
  )
}
