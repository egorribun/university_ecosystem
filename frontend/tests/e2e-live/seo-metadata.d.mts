export interface SeoMetadata {
  title: string
  titleCount: number
  metaTitle: string | null
  description: string | null
  descriptionCount: number
  ogType: string | null
  ogTitle: string | null
  ogDescription: string | null
  ogImage: string | null
  twitterCard: string | null
  twitterTitle: string | null
  twitterDescription: string | null
  twitterImage: string | null
  seoMetaCounts: Record<string, number>
}

export function normalizeMetadataText(value: string): string
export function extractSeoMetadata(markup: string | null): SeoMetadata | null
export function matchesRequestedCatalogTitle(
  language: string,
  catalogs: Readonly<Record<string, Readonly<{ pageTitle?: unknown }> | undefined>>,
  renderedTitle: string
): boolean
