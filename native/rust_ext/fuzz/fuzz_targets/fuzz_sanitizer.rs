#![no_main]

use ammonia::Builder;
use libfuzzer_sys::fuzz_target;
use std::collections::{HashMap, HashSet};

fn sanitize_rich_text(html: &str) -> String {
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

fn sanitize_html_basic(html: &str) -> String {
    let allowed_tags: HashSet<&str> = ["b", "i", "em", "strong"].iter().copied().collect();
    Builder::new().tags(allowed_tags).clean(html).to_string()
}

fn strip_html(html: &str) -> String {
    Builder::new().tags(HashSet::new()).clean(html).to_string()
}

fuzz_target!(|data: &[u8]| {
    // Only process valid UTF-8 — all Python strings are UTF-8.
    if let Ok(s) = std::str::from_utf8(data) {
        let _ = sanitize_rich_text(s);
        let _ = sanitize_html_basic(s);
        let _ = strip_html(s);
    }
});
