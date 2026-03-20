use ammonia::Builder;
use std::collections::{HashSet, HashMap};
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn sanitize_rich_text(html: &str) -> String {
    let mut tags = HashSet::new();
    let allowed_tags = [
        "p", "br", "b", "i", "em", "strong", "u", "s", "strike",
        "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
        "a", "blockquote", "code", "pre"
    ];
    for t in allowed_tags {
        tags.insert(t);
    }

    let mut attributes = HashMap::new();
    let mut a_attrs = HashSet::new();
    a_attrs.insert("href");
    a_attrs.insert("title");
    a_attrs.insert("target");
    attributes.insert("a", a_attrs);

    let mut url_schemes = HashSet::new();
    url_schemes.insert("http");
    url_schemes.insert("https");

    Builder::new()
        .tags(tags)
        .tag_attributes(attributes)
        .url_schemes(url_schemes)
        // ammonia automatically handles rel="noopener noreferrer" for target="_blank"
        .link_rel(Some("noopener noreferrer"))
        // We do not want to allow relative URLs for this strict sanitizer
        // Or if we do, ammonia's default handles it. Let's strictly disallow data:/javascript:
        .clean(html)
        .to_string()
}

#[wasm_bindgen]
pub fn sanitize_html_basic(html: &str) -> String {
    let mut tags = HashSet::new();
    for t in ["b", "i", "em", "strong"] {
        tags.insert(t);
    }
    Builder::new()
        .tags(tags)
        .clean(html)
        .to_string()
}

#[wasm_bindgen]
pub fn strip_html(html: &str) -> String {
    Builder::new()
        .tags(HashSet::new())
        .clean(html)
        .to_string()
}
