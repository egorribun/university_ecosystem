use ammonia::Builder;
use std::collections::{HashMap, HashSet};
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn sanitize_rich_text(html: &str) -> String {
    let mut tags = HashSet::new();
    let allowed_tags = [
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
    Builder::new().tags(tags).clean(html).to_string()
}

#[wasm_bindgen]
pub fn strip_html(html: &str) -> String {
    Builder::new().tags(HashSet::new()).clean(html).to_string()
}

#[wasm_bindgen]
#[allow(clippy::not_unsafe_ptr_arg_deref)]
pub fn sanitize_rich_text_raw(ptr: *const u8, len: usize) -> Result<String, String> {
    if ptr.is_null() {
        return Err(String::from("Null pointer"));
    }

    #[cfg(target_arch = "wasm32")]
    {
        let mem_size = core::arch::wasm32::memory_size::<0>() * 65536;
        let start = ptr as usize;
        if start > mem_size || len > mem_size || start.saturating_add(len) > mem_size {
            return Err(String::from("Out of bounds pointer/length"));
        }
    }

    let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
    let s = std::str::from_utf8(slice).map_err(|e| format!("Invalid UTF-8: {}", e))?;

    Ok(sanitize_rich_text(s))
}

// Native unit tests (testing session 9). #[wasm_bindgen] leaves the functions
// callable as plain Rust on a non-wasm target, and ammonia is a native crate,
// so these exercise the exact sanitization code paths the browser runs. The
// crate-type already includes "rlib", so no Cargo.toml change is needed. The
// browser parity is deliberately NOT re-run via wasm-pack here: pure Rust ->
// identical code paths (wasm-sanitizer has no JS-only branches). Assertions are
// presence/absence based to stay robust across ammonia minor versions.
#[cfg(all(test, not(target_arch = "wasm32")))]
mod tests {
    use super::*;

    #[test]
    fn rich_text_strips_script_element_and_content() {
        let out = sanitize_rich_text("<p>safe</p><script>alert('xss')</script>");
        assert!(out.contains("safe"), "allowed text must survive: {out}");
        assert!(
            !out.contains("<script"),
            "script tag must be removed: {out}"
        );
        assert!(
            !out.contains("alert"),
            "script content must be removed: {out}"
        );
    }

    #[test]
    fn rich_text_strips_onerror_handler_and_img() {
        let out = sanitize_rich_text("<img src=x onerror=alert(1)>");
        assert!(
            !out.contains("onerror"),
            "event handler must be stripped: {out}"
        );
        assert!(
            !out.contains("<img"),
            "img is not in the allowed tag set: {out}"
        );
    }

    #[test]
    fn rich_text_drops_javascript_scheme_href() {
        let out = sanitize_rich_text(r#"<a href="javascript:alert(1)">click</a>"#);
        assert!(out.contains("click"), "link text must survive: {out}");
        assert!(
            !out.contains("javascript:"),
            "javascript: scheme must be dropped: {out}"
        );
    }

    #[test]
    fn rich_text_drops_data_scheme_href() {
        let out = sanitize_rich_text(r#"<a href="data:text/html,<script>1</script>">x</a>"#);
        assert!(
            !out.contains("data:"),
            "data: scheme must be dropped: {out}"
        );
        assert!(
            !out.contains("<script"),
            "embedded script must be gone: {out}"
        );
    }

    #[test]
    fn rich_text_keeps_https_link_with_noopener_rel() {
        let out = sanitize_rich_text(r#"<a href="https://example.com" target="_blank">go</a>"#);
        assert!(
            out.contains(r#"href="https://example.com""#),
            "https href must survive: {out}"
        );
        assert!(out.contains("noopener"), "rel must include noopener: {out}");
        assert!(
            out.contains("noreferrer"),
            "rel must include noreferrer: {out}"
        );
    }

    #[test]
    fn rich_text_keeps_allowed_formatting_tags() {
        let out = sanitize_rich_text("<p><strong>bold</strong> and <em>em</em></p>");
        assert!(
            out.contains("<strong>bold</strong>"),
            "strong must survive: {out}"
        );
        assert!(out.contains("<em>em</em>"), "em must survive: {out}");
    }

    #[test]
    fn rich_text_strips_unknown_tag_but_keeps_text() {
        let out = sanitize_rich_text("<div class=evil>content</div>");
        assert!(out.contains("content"), "text must survive: {out}");
        assert!(
            !out.contains("<div"),
            "div is not in the rich-text allow list: {out}"
        );
    }

    #[test]
    fn basic_keeps_only_inline_emphasis_tags() {
        let out = sanitize_html_basic("<p>para</p><b>bold</b><script>x</script>");
        assert!(out.contains("<b>bold</b>"), "b must survive: {out}");
        assert!(
            out.contains("para"),
            "stripped-tag text must survive: {out}"
        );
        assert!(
            !out.contains("<p>"),
            "p is not in the basic allow list: {out}"
        );
        assert!(!out.contains("<script"), "script must be removed: {out}");
    }

    #[test]
    fn basic_removes_anchor_tags() {
        let out = sanitize_html_basic(r#"<a href="https://x.com">link</a>"#);
        assert!(out.contains("link"), "anchor text must survive: {out}");
        assert!(
            !out.contains("<a"),
            "anchors are not allowed in basic mode: {out}"
        );
    }

    #[test]
    fn strip_html_removes_all_tags_keeps_text() {
        let out = strip_html("<b>hi</b> <i>there</i><script>nope</script>");
        assert!(out.contains("hi"), "text must survive: {out}");
        assert!(out.contains("there"), "text must survive: {out}");
        assert!(!out.contains('<'), "no tags may remain: {out}");
        assert!(
            !out.contains("nope"),
            "script content must be removed: {out}"
        );
    }

    #[test]
    fn strip_html_is_idempotent_on_plain_text() {
        let plain = "just plain text, no markup";
        assert_eq!(strip_html(plain), plain);
        assert_eq!(strip_html(&strip_html("<b>x</b>")), strip_html("<b>x</b>"));
    }

    #[test]
    fn sanitizers_handle_empty_input() {
        assert_eq!(sanitize_rich_text(""), "");
        assert_eq!(sanitize_html_basic(""), "");
        assert_eq!(strip_html(""), "");
    }

    #[test]
    fn test_raw_pointer_null_and_utf8() {
        let res = sanitize_rich_text_raw(std::ptr::null(), 10);
        assert!(res.is_err());

        let invalid_utf8 = [0, 159, 146, 150]; // invalid starting byte
        let res = sanitize_rich_text_raw(invalid_utf8.as_ptr(), invalid_utf8.len());
        assert!(res.is_err());

        let valid_utf8 = b"<p>hello</p>";
        let res = sanitize_rich_text_raw(valid_utf8.as_ptr(), valid_utf8.len());
        assert_eq!(res.unwrap(), "<p>hello</p>");
    }
}

#[cfg(all(test, target_arch = "wasm32"))]
mod wasm_tests {
    use super::*;
    use wasm_bindgen_test::*;

    #[wasm_bindgen_test]
    fn test_rich_text() {
        let out = sanitize_rich_text("<p>Hello <b>world</b></p>");
        assert!(
            out.contains("<p>Hello <b>world</b></p>"),
            "wasm rich text: {}",
            out
        );
    }

    #[wasm_bindgen_test]
    fn test_basic() {
        let out = sanitize_html_basic("<b>bold</b> and <i>italic</i>");
        assert!(out.contains("<b>bold</b>"), "wasm basic: {}", out);
    }

    #[wasm_bindgen_test]
    fn test_strip() {
        let out = strip_html("<p>Hello <b>world</b></p>");
        assert_eq!(out, "Hello world", "wasm strip: {}", out);
    }
    #[wasm_bindgen_test]
    fn test_raw_pointer_wasm_oob() {
        // Test null pointer
        let res = sanitize_rich_text_raw(std::ptr::null(), 10);
        assert!(res.is_err());

        // Test pointer out of bounds
        let out_of_bounds_ptr = 999_999_999 as *const u8;
        let res = sanitize_rich_text_raw(out_of_bounds_ptr, 100);
        assert!(res.is_err());
    }
}
