//! Python bindings for the university-ecosystem HTML sanitizer.
//!
//! Exposes the same three sanitization functions as the WASM frontend crate
//! (`frontend/wasm-sanitizer/src/lib.rs`) but via a native CPython extension
//! so the Python backend can call the identical Rust/ammonia AST.
//!
//! This eliminates architectural drift: frontend (WASM) and backend (PyO3)
//! run the same ammonia configuration, so a given HTML string will always
//! produce the same sanitized output on both sides.

use ammonia::Builder;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

/// Remove dangerous HTML while preserving rich-text formatting.
///
/// Allowed elements: paragraphs, headings, lists, inline formatting,
/// blockquotes, code/pre, and anchors (href/title/target only).
/// All URLs must use http or https. Links automatically get
/// `rel="noopener noreferrer"`.
#[pyfunction]
pub fn sanitize_rich_text(html: &str) -> String {
    let allowed_tags: HashSet<&str> = [
        "p", "br", "b", "i", "em", "strong", "u", "s", "strike",
        "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
        "a", "blockquote", "code", "pre",
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

/// Strip all HTML except basic inline formatting (bold, italic, emphasis).
///
/// Use this for short user-supplied strings (e.g. display names, titles)
/// where rich formatting is unwanted.
#[pyfunction]
pub fn sanitize_html_basic(html: &str) -> String {
    let allowed_tags: HashSet<&str> = ["b", "i", "em", "strong"].iter().copied().collect();
    Builder::new()
        .tags(allowed_tags)
        .clean(html)
        .to_string()
}

/// Remove all HTML tags, returning plain text.
///
/// Use this when storing or indexing content where markup must be absent.
#[pyfunction]
pub fn strip_html(html: &str) -> String {
    Builder::new()
        .tags(HashSet::new())
        .clean(html)
        .to_string()
}

/// pyo3_sanitizer — native Python extension module.
///
/// Import as: `import pyo3_sanitizer`
/// Falls back to the `nh3` Python package if this extension is unavailable
/// (see `app/services/content_processing.py`).
#[pymodule]
fn pyo3_sanitizer(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sanitize_rich_text, module)?)?;
    module.add_function(wrap_pyfunction!(sanitize_html_basic, module)?)?;
    module.add_function(wrap_pyfunction!(strip_html, module)?)?;
    Ok(())
}
