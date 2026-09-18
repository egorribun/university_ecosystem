//! Pure Rust HTML sanitization shared by the native binding and fuzz targets.
//!
//! Keeping this module independent from PyO3 is deliberate: fuzz executables
//! are standalone binaries and must not inherit the unresolved-symbol linking
//! contract required by a CPython extension module.

use ammonia::Builder;
use std::collections::{HashMap, HashSet};

/// Remove parser markers that are not meaningful application content.
///
/// html5ever (which powers ammonia) preserves NUL and BOM code points in text
/// nodes. They can influence tokenization when a sanitized fragment is parsed
/// again, so normalize them between canonicalization passes as well as before
/// returning to the caller.
fn strip_unsafe_markers(value: String) -> String {
    value.replace(['\0', '\u{feff}'], "")
}

fn sanitize_rich_text_once(html: &str) -> String {
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

    Builder::new()
        .tags(allowed_tags)
        .tag_attributes(attributes)
        .url_schemes(url_schemes)
        .link_rel(Some("noopener noreferrer"))
        .clean(html)
        .to_string()
}

fn sanitize_html_basic_once(html: &str) -> String {
    let allowed_tags: HashSet<&str> = ["b", "i", "em", "strong"].iter().copied().collect();
    Builder::new().tags(allowed_tags).clean(html).to_string()
}

fn strip_html_once(html: &str) -> String {
    Builder::new().tags(HashSet::new()).clean(html).to_string()
}

/// Canonicalize an ammonia fragment until another pass is a no-op.
///
/// html5ever may repair malformed fragments over more than one parse/serialize
/// cycle. Keep the loop bounded so hostile input cannot consume unbounded CPU;
/// in practice the parser reaches a fixed point well before this limit. Each
/// pass uses the same restrictive sanitizer, and unsafe marker normalization is
/// performed before comparing/returning the representation.
fn canonicalize(html: &str, clean_once: fn(&str) -> String) -> String {
    const MAX_PASSES: usize = 8;

    let mut current = strip_unsafe_markers(clean_once(html));
    for _ in 1..MAX_PASSES {
        let next = strip_unsafe_markers(clean_once(&current));
        if next == current {
            return current;
        }
        current = next;
    }
    current
}

/// Remove dangerous HTML while preserving rich-text formatting.
///
/// Allowed elements: paragraphs, headings, lists, inline formatting,
/// blockquotes, code/pre, and anchors (href/title/target only).
/// All URLs must use http or https. Links automatically get
/// `rel="noopener noreferrer"`.
pub fn sanitize_rich_text(html: &str) -> String {
    // WHY: html5ever's tree builder repairs malformed fragments (for example,
    // an unclosed heading followed by another heading).  The first serialized
    // representation can therefore still be reparsed into a different tree.
    // Canonicalize that representation before returning it. Every pass uses
    // the same restrictive allow-list and URL policy, so this cannot introduce
    // markup that a single pass would have rejected.
    canonicalize(html, sanitize_rich_text_once)
}

/// Strip all HTML except basic inline formatting (bold, italic, emphasis).
///
/// Use this for short user-supplied strings (e.g. display names, titles)
/// where rich formatting is unwanted.
pub fn sanitize_html_basic(html: &str) -> String {
    canonicalize(html, sanitize_html_basic_once)
}

/// Remove all HTML tags, returning plain text.
///
/// Use this when storing or indexing content where markup must be absent.
pub fn strip_html(html: &str) -> String {
    canonicalize(html, strip_html_once)
}

#[cfg(test)]
mod regression_tests {
    use super::{canonicalize, sanitize_rich_text};

    #[test]
    fn malformed_html_fuzz_regression_is_idempotent() {
        let input = "*zq**<h2>\u{18}nav**<h*<h2><h2><5>bdo";
        let once = sanitize_rich_text(input);
        let twice = sanitize_rich_text(&once);
        assert_eq!(once, twice);
    }

    #[test]
    fn canonicalization_is_bounded_for_non_converging_cleaner() {
        fn append_marker(value: &str) -> String {
            format!("{value}x")
        }

        assert_eq!(canonicalize("", append_marker), "xxxxxxxx");
    }
}
