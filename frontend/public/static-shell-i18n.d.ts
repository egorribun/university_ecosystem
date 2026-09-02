export type SupportedLanguage = "ru" | "en";

export interface MetaStrings {
  title: string;
  description: string;
  ogTitle?: string;
  ogDescription?: string;
  twitterTitle?: string;
  twitterDescription?: string;
  ogLocale?: string;
}

export interface OfflineStrings {
  pageTitle: string;
  title: string;
  description: string;
  hints?: string[];
  retry: string;
  footer: string;
}

export interface NotFoundStrings {
  pageTitle: string;
  title: string;
  description: string;
  home: string;
  login: string;
}

export interface ManifestShortcutStrings {
  name: string;
  description?: string;
}

export interface ManifestStrings {
  name: string;
  short_name: string;
  description: string;
  shortcuts?: ManifestShortcutStrings[];
}

export interface TranslationBundle {
  meta?: MetaStrings;
  offline?: OfflineStrings;
  notFound?: NotFoundStrings;
  manifest: ManifestStrings;
}

export const storageKey: string;
export const fallbackLanguage: SupportedLanguage;
export const supportedLanguages: SupportedLanguage[];
export const translations: Record<SupportedLanguage, TranslationBundle>;

export function detectLanguage(options?: {
  storedLanguage?: string | null;
  navigatorLanguage?: string;
}): SupportedLanguage;

export function getPreferredLanguage(win?: Window): SupportedLanguage;

export function getStrings(language: string | undefined): TranslationBundle;
export function getManifestStrings(language: string | undefined): ManifestStrings;
export function getManifestPath(language: string | undefined): string;

export function applyDocumentLanguage(doc: Document | undefined, language: string | undefined): void;
export function applyMetaTranslations(doc: Document | undefined, language: string | undefined): void;
export function applyOfflineTranslations(doc: Document | undefined, language: string | undefined): void;
export function applyNotFoundTranslations(doc: Document | undefined, language: string | undefined): void;
