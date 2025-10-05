import DOMPurify, { type Config } from "dompurify";
import type { TrustedHTML, TrustedTypePolicyFactory } from "trusted-types/lib";

type TrustedPolicy = ReturnType<TrustedTypePolicyFactory["createPolicy"]>;

const HTML_CONFIG: Config = Object.freeze({
  USE_PROFILES: { html: true },
  ALLOW_DATA_ATTR: false,
  KEEP_CONTENT: false,
});

const TEXT_CONFIG: Config = Object.freeze({
  ALLOWED_TAGS: [],
  ALLOWED_ATTR: [],
  KEEP_CONTENT: false,
});

type TrustedTypesWindow = Window & {
  trustedTypes?: TrustedTypePolicyFactory;
  __dompurifyNewsPolicy?: TrustedPolicy | false;
};

const createPolicy = (win: TrustedTypesWindow): TrustedPolicy | null => {
  if (!win.trustedTypes) return null;
  if (win.__dompurifyNewsPolicy === false) return null;
  if (win.__dompurifyNewsPolicy) return win.__dompurifyNewsPolicy;
  try {
    win.__dompurifyNewsPolicy = win.trustedTypes.createPolicy("dompurify-news", {
      createHTML: (dirty: string) => DOMPurify.sanitize(dirty, HTML_CONFIG),
    });
  } catch (error) {
    // eslint-disable-next-line no-console -- surfacing policy errors helps with CSP debugging
    console.warn("Unable to create dompurify-news trusted types policy", error);
    win.__dompurifyNewsPolicy = false;
  }
  return win.__dompurifyNewsPolicy || null;
};

export const sanitizeNewsHtml = (dirty: string | null | undefined): string | TrustedHTML => {
  const source = dirty ?? "";
  if (typeof window !== "undefined") {
    const win = window as TrustedTypesWindow;
    const policy = createPolicy(win);
    if (policy) {
      return policy.createHTML(source);
    }
  }
  return DOMPurify.sanitize(source, HTML_CONFIG);
};

export const sanitizeNewsText = (dirty: string | null | undefined): string => {
  return DOMPurify.sanitize(dirty ?? "", TEXT_CONFIG) as string;
};
