import { htmlToPlainText } from "@/utils/htmlText"

/**
 * Generates a URL-safe slug from text.
 * Supports Unicode (Cyrillic headings produce valid slugs).
 * Shared between marked heading renderer and useArticleHeadings hook
 * to guarantee matching IDs for ToC linking.
 */
export function slugify(text: string): string {
  return htmlToPlainText(text)
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 64)
}
