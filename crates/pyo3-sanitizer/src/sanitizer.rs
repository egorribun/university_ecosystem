//! Pure Rust HTML sanitization shared by the native binding and fuzz targets.
//!
//! Keeping this module independent from PyO3 is deliberate: fuzz executables
//! are standalone binaries and must not inherit the unresolved-symbol linking
//! contract required by a CPython extension module.

use ammonia::Builder;
use std::collections::{HashMap, HashSet};

/// Remove dangerous HTML while preserving rich-text formatting.
///
/// Allowed elements: paragraphs, headings, lists, inline formatting,
/// blockquotes, code/pre, and anchors (href/title/target only).
/// All URLs must use http or https. Links automatically get
/// `rel="noopener noreferrer"`.
pub fn sanitize_rich_text(html: &str) -> String {
    let allowed_tags: HashSet<&str> = [
        "p",
        "br",
        "b",
        "i",
        "em",
        "strong",
        "u",
        "s",
        "strike",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "a",
        "blockquote",
        "code",
        "pre",
    ]
    .iter()
    .copied()
    .collect();

    let mut attributes: HashMap<&str, HashSet<&str>> = HashMap::new();
    attributes.insert("a", ["href", "title", "target"].iter().copied().collect());

    let url_schemes: HashSet<&str> = ["http", "https"].iter().copied().collect();

    // WHY: html5ever (used internally by ammonia) processes null bytes (\0)
    // as part of text nodes rather than removing them outright. When \0
    // precedes U+FEFF, the tokeniser leaves FEFF in the first-pass output but
    // removes it on the second pass — breaking idempotency. Stripping both
    // characters post-ammonia is the minimal correct fix.
    Builder::new()
        .tags(allowed_tags)
        .tag_attributes(attributes)
        .url_schemes(url_schemes)
        .link_rel(Some("noopener noreferrer"))
        .clean(html)
        .to_string()
        .replace(['\0', '\u{feff}'], "")
}

/// Strip all HTML except basic inline formatting (bold, italic, emphasis).
///
/// Use this for short user-supplied strings (e.g. display names, titles)
/// where rich formatting is unwanted.
pub fn sanitize_html_basic(html: &str) -> String {
    let allowed_tags: HashSet<&str> = ["b", "i", "em", "strong"].iter().copied().collect();
    // WHY: same html5ever null-byte + BOM idempotency issue as strip_html.
    Builder::new()
        .tags(allowed_tags)
        .clean(html)
        .to_string()
        .replace(['\0', '\u{feff}'], "")
}

/// Remove all HTML tags, returning plain text.
///
/// Use this when storing or indexing content where markup must be absent.
pub fn strip_html(html: &str) -> String {
    // Run ammonia's tag-stripping pass first.
    let cleaned = Builder::new().tags(HashSet::new()).clean(html).to_string();

    // WHY: html5ever (used internally by ammonia) processes null bytes (\0)
    // as part of text nodes rather than removing them outright. When \0
    // precedes a BOM/ZWNBSP (U+FEFF), the presence of \0 changes how the HTML5
    // tokeniser handles U+FEFF on the first call (leaving it in the output)
    // while the second call (now without \0) removes it — breaking
    // idempotency. Stripping both characters after ammonia runs is the
    // minimal, correct fix that restores the invariant:
    //   strip_html(strip_html(x)) == strip_html(x)  for all x.
    cleaned.replace(['\0', '\u{feff}'], "")
}
