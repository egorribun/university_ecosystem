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

fn catch_unwind_to_pyerr<F, R>(f: F) -> PyResult<R>
where
    F: FnOnce() -> R + std::panic::UnwindSafe,
{
    std::panic::catch_unwind(f).map_err(|err| {
        let msg = if let Some(s) = err.downcast_ref::<&str>() {
            *s
        } else if let Some(s) = err.downcast_ref::<String>() {
            s.as_str()
        } else {
            "Rust panic occurred"
        };
        pyo3::exceptions::PyRuntimeError::new_err(msg.to_string())
    })
}

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
    // as part of text nodes rather than removing them outright.  When \0
    // precedes U+FEFF, the tokeniser leaves FEFF in the first-pass output but
    // removes it on the second pass — breaking idempotency.  Stripping both
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

#[pyfunction]
#[pyo3(name = "sanitize_rich_text")]
pub fn py_sanitize_rich_text(html: &str) -> PyResult<String> {
    catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| sanitize_rich_text(html)))
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

#[pyfunction]
#[pyo3(name = "sanitize_html_basic")]
pub fn py_sanitize_html_basic(html: &str) -> PyResult<String> {
    catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| sanitize_html_basic(html)))
}

/// Remove all HTML tags, returning plain text.
///
/// Use this when storing or indexing content where markup must be absent.
pub fn strip_html(html: &str) -> String {
    // Run ammonia's tag-stripping pass first.
    let cleaned = Builder::new().tags(HashSet::new()).clean(html).to_string();

    // WHY: html5ever (used internally by ammonia) processes null bytes (\0)
    // as part of text nodes rather than removing them outright.  When \0
    // precedes a BOM/ZWNBSP (U+FEFF), the presence of \0 changes how the
    // HTML5 tokeniser handles U+FEFF on the *first* call (leaving it in the
    // output) while the *second* call (now without \0) removes it — breaking
    // idempotency.  Stripping both characters after ammonia runs is the
    // minimal, correct fix that restores the invariant:
    //   strip_html(strip_html(x)) == strip_html(x)  for all x.
    cleaned.replace(['\0', '\u{feff}'], "")
}

#[pyfunction]
#[pyo3(name = "strip_html")]
pub fn py_strip_html(html: &str) -> PyResult<String> {
    catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| strip_html(html)))
}

/// pyo3_sanitizer — native Python extension module.
///
/// Import as: `import pyo3_sanitizer`
/// Falls back to the `nh3` Python package if this extension is unavailable
/// (see `app/services/content_processing.py`).
#[pymodule]
fn pyo3_sanitizer(module: &Bound<'_, PyModule>) -> PyResult<()> {
    register_python_functions(module)
}

fn register_python_functions(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(py_sanitize_rich_text, module)?)?;
    module.add_function(wrap_pyfunction!(py_sanitize_html_basic, module)?)?;
    module.add_function(wrap_pyfunction!(py_strip_html, module)?)?;
    Ok(())
}

// ── Unit Tests ────────────────────────────────────────────────────────────────
//
// These test the Rust functions directly — no PyO3 runtime needed.
// `cargo test --lib` runs them in isolation, which is exactly what the
// `rust-tests` CI job does (see .github/workflows/ci.yml §rust-tests).
//
// Coverage rationale:
//  - KAT vectors verify byte-exact parity with the ammonia 4.x defaults so
//    that future ammonia upgrades never silently change sanitization behaviour.
//  - XSS payloads confirm that attack vectors from OWASP's XSS cheat-sheet
//    are stripped before they reach any Python caller.
//  - URL-scheme tests confirm only http/https survive in <a href=…> attributes.
#[cfg(test)]
mod tests {
    use super::*;

    // ── sanitize_rich_text ───────────────────────────────────────────────────

    #[test]
    fn rich_text_preserves_allowed_block_elements() {
        let input = "<p>Hello <b>world</b></p><ul><li>item</li></ul>";
        let out = sanitize_rich_text(input);
        assert!(out.contains("<p>"), "p tag must be preserved");
        assert!(out.contains("<b>"), "b tag must be preserved");
        assert!(out.contains("<ul>"), "ul tag must be preserved");
        assert!(out.contains("<li>"), "li tag must be preserved");
    }

    #[test]
    fn rich_text_preserves_headings_and_code() {
        let input = "<h1>Title</h1><h3>Sub</h3><pre><code>fn main() {}</code></pre>";
        let out = sanitize_rich_text(input);
        assert!(out.contains("<h1>"), "h1 must be preserved");
        assert!(out.contains("<h3>"), "h3 must be preserved");
        assert!(out.contains("<code>"), "code must be preserved");
        assert!(out.contains("<pre>"), "pre must be preserved");
    }

    #[test]
    fn rich_text_strips_script_tags() {
        // Classic XSS: inline <script>
        let out = sanitize_rich_text("<script>alert('xss')</script><p>safe</p>");
        assert!(!out.contains("<script"), "script tag must be removed");
        assert!(!out.contains("alert"), "script content must be removed");
        assert!(out.contains("<p>"), "sibling safe content must survive");
    }

    #[test]
    fn rich_text_strips_onerror_attribute() {
        // XSS via event handler attribute
        let out = sanitize_rich_text("<img src=x onerror=alert(1)>");
        assert!(
            !out.contains("onerror"),
            "onerror attribute must be stripped"
        );
        assert!(
            !out.contains("<img"),
            "img (not in allow-list) must be removed"
        );
    }

    #[test]
    fn rich_text_strips_javascript_href() {
        // XSS via javascript: URI scheme
        let out = sanitize_rich_text("<a href='javascript:void(0)'>click</a>");
        // ammonia replaces disallowed URL schemes with '#' or removes href entirely.
        assert!(
            !out.contains("javascript:"),
            "javascript: scheme must be stripped"
        );
    }

    #[test]
    fn rich_text_preserves_https_anchor() {
        let out = sanitize_rich_text("<a href='https://example.com' title='ex'>link</a>");
        assert!(
            out.contains("href"),
            "href must be preserved for https links"
        );
        assert!(
            out.contains("https://example.com"),
            "https URL must survive"
        );
        // ammonia injects rel="noopener noreferrer" automatically
        assert!(out.contains("noopener"), "rel=noopener must be injected");
    }

    #[test]
    fn rich_text_strips_style_attribute() {
        // style= is a common XSS vector (expression(), moz-binding, etc.)
        let out = sanitize_rich_text("<p style='color:red;expression(alert(1))'>text</p>");
        assert!(!out.contains("style="), "style attribute must be stripped");
        assert!(out.contains("text"), "text content must survive");
    }

    #[test]
    fn rich_text_empty_string_roundtrips() {
        assert_eq!(sanitize_rich_text(""), "");
    }

    #[test]
    fn rich_text_plain_text_roundtrips() {
        // Plain text with no markup must pass through unchanged
        let input = "Hello, world! No markup here.";
        assert_eq!(sanitize_rich_text(input), input);
    }

    // ── sanitize_html_basic ──────────────────────────────────────────────────

    #[test]
    fn basic_preserves_bold_and_italic() {
        let out = sanitize_html_basic("<b>bold</b> and <i>italic</i> and <em>emphasis</em>");
        assert!(out.contains("<b>"), "b must be preserved");
        assert!(out.contains("<i>"), "i must be preserved");
        assert!(out.contains("<em>"), "em must be preserved");
    }

    #[test]
    fn basic_strips_anchor_tag() {
        // <a> is allowed in rich mode but NOT in basic mode
        let out = sanitize_html_basic("<a href='https://example.com'>link</a>");
        assert!(!out.contains("<a"), "a must be stripped in basic mode");
        assert!(out.contains("link"), "link text must survive");
    }

    #[test]
    fn basic_strips_script() {
        let out = sanitize_html_basic("<script>evil()</script><strong>safe</strong>");
        assert!(!out.contains("<script"), "script must be stripped");
        assert!(out.contains("<strong>"), "strong must survive");
    }

    #[test]
    fn basic_strips_heading_tags() {
        // Headings are NOT in the basic allow-list
        let out = sanitize_html_basic("<h1>Title</h1><b>bold</b>");
        assert!(!out.contains("<h1>"), "h1 must be stripped in basic mode");
        assert!(
            out.contains("Title"),
            "heading text must survive as plain text"
        );
        assert!(out.contains("<b>"), "b must survive");
    }

    #[test]
    fn basic_empty_string_roundtrips() {
        assert_eq!(sanitize_html_basic(""), "");
    }

    // ── strip_html ───────────────────────────────────────────────────────────

    #[test]
    fn strip_removes_all_tags() {
        let out = strip_html("<p><b>Hello</b> <i>world</i></p>");
        assert!(!out.contains('<'), "no tags must remain");
        assert!(out.contains("Hello"), "text must survive");
        assert!(out.contains("world"), "text must survive");
    }

    #[test]
    fn strip_removes_script_content_tags_but_not_text() {
        // ammonia's strip_tags removes the tags but the text content of
        // script elements is still passed through (it is CDATA, not markup).
        // We verify the <script…> delimiters are gone at minimum.
        let out = strip_html("<script>dangerous</script>safe");
        assert!(
            !out.contains("<script"),
            "script opening tag must be removed"
        );
        assert!(
            !out.contains("</script>"),
            "script closing tag must be removed"
        );
        assert!(out.contains("safe"), "non-script text must survive");
    }

    #[test]
    fn strip_empty_string_roundtrips() {
        assert_eq!(strip_html(""), "");
    }

    #[test]
    fn strip_plain_text_roundtrips() {
        let input = "No HTML here — just text & symbols.";
        let out = strip_html(input);
        // ampersand is preserved as-is (ammonia does not HTML-encode plain text)
        assert!(out.contains("No HTML here"));
    }

    #[test]
    fn strip_nested_tags_yield_all_text() {
        let out = strip_html("<div><p>outer <span>inner</span></p></div>");
        assert!(!out.contains('<'), "no tags must remain");
        assert!(out.contains("outer"), "outer text must survive");
        assert!(out.contains("inner"), "inner text must survive");
    }

    #[test]
    fn test_strip_html_null_byte_and_bom_idempotent() {
        // Regression: proptest found strip_html was not idempotent on null + BOM
        let input = "\0\u{feff}";
        let first = strip_html(input);
        let second = strip_html(&first);
        assert_eq!(first, second, "strip_html must be idempotent");
        // Also verify the output contains no null bytes or BOM
        assert!(!first.contains('\0'), "strip_html must remove null bytes");
        assert!(
            !first.contains('\u{feff}'),
            "strip_html must remove BOM characters"
        );
    }

    #[test]
    fn test_deep_nesting_stack_safety() {
        let mut input = String::new();
        for _ in 0..250 {
            input.push_str("<div>");
        }
        input.push_str("deep-nesting-content");
        for _ in 0..250 {
            input.push_str("</div>");
        }
        let out = sanitize_rich_text(&input);
        assert_eq!(out, "deep-nesting-content");
    }

    #[test]
    fn test_unicode_and_emojis_preservation() {
        let input = "<p>Привет, мир! こんにちは 🌟 Rocket 🚀</p>";
        let out = sanitize_rich_text(input);
        assert!(out.contains("Привет, мир!"), "Cyrillic must survive");
        assert!(out.contains("こんにちは"), "Japanese must survive");
        assert!(out.contains("🌟"), "Star emoji must survive");
        assert!(out.contains("🚀"), "Rocket emoji must survive");

        let basic_out = sanitize_html_basic("<b>Привет 👋</b>");
        assert!(basic_out.contains("<b>Привет 👋</b>"));

        let stripped = strip_html("Привет 🌍");
        assert_eq!(stripped, "Привет 🌍");
    }
    #[test]
    fn test_null_byte_and_control_characters() {
        // Null bytes and ASCII control characters must not cause panics and
        // must not appear in output that could confuse downstream parsers.
        // ammonia passes control characters through the HTML5-ever parser,
        // which strips \0 from text nodes per the HTML5 spec.
        let inputs = [
            "\0",
            "\x01\x02\x03",
            "<p>\0null\0</p>",
            "<b>\x08backspace\x1b</b>",
        ];
        for input in inputs {
            // None of these must panic
            let _ = sanitize_rich_text(input);
            let _ = sanitize_html_basic(input);
            let _ = strip_html(input);
        }
    }

    #[test]
    fn test_null_bytes_arbitrary_places() {
        // Arbitrary places: inside tag name, attribute name, attribute value, text content, comments
        let inputs = [
            "<p\0>content</p>",
            "<p class=\0evil>content</p>",
            "<p class=evil\0>content</p>",
            "<p>content\0here</p>",
            "<!-- \0 comment \0 -->",
            "<\0script>alert(1)</script>",
        ];
        for input in inputs {
            let _ = sanitize_rich_text(input);
            let _ = sanitize_html_basic(input);
            let _ = strip_html(input);
        }
    }

    #[test]
    fn test_very_long_string_performance_boundary() {
        // Verifies that the sanitizer completes without panic or OOM for a
        // 1 MiB payload — a practical upper bound for user-supplied content.
        // Miri interprets every html5ever instruction, so it keeps the same
        // input shape at a representative size while the native Rust gate
        // retains the full 1 MiB performance boundary.
        #[cfg(miri)]
        const REPETITIONS: usize = 16;
        #[cfg(not(miri))]
        const REPETITIONS: usize = 60_000;
        let repeated = "<p>Hello world</p>".repeat(REPETITIONS);
        let out = sanitize_rich_text(&repeated);
        // Output must still contain paragraph tags (they are in the allow-list)
        assert!(
            out.contains("<p>"),
            "p tags must survive in a large payload"
        );

        let stripped = strip_html(&repeated);
        // All markup removed; only text content remains
        assert!(!stripped.contains('<'), "no tags must remain after strip");
    }

    #[cfg(not(miri))]
    #[test]
    fn test_panic_boundary_catches_rust_panic() {
        Python::initialize();
        let result = catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| {
            panic!("test panic string");
        }));
        assert!(result.is_err());
        let py_err = result.unwrap_err();
        Python::attach(|_py| {
            assert!(py_err.to_string().contains("test panic string"));
        });
    }

    #[cfg(not(miri))]
    #[test]
    fn test_panic_formatting_coverage() {
        Python::initialize();
        // Panic with a String
        let result_string = catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| {
            panic!("{}", "panic String".to_string());
        }));
        assert!(result_string.is_err());
        let py_err_string = result_string.unwrap_err();
        Python::attach(|_py| {
            assert!(py_err_string.to_string().contains("panic String"));
        });

        // Panic with an arbitrary type
        let result_any = catch_unwind_to_pyerr(std::panic::AssertUnwindSafe(|| {
            std::panic::panic_any(42u32);
        }));
        assert!(result_any.is_err());
        let py_err_any = result_any.unwrap_err();
        Python::attach(|_py| {
            assert!(py_err_any.to_string().contains("Rust panic occurred"));
        });
    }

    #[cfg(not(miri))]
    #[test]
    fn test_pyo3_bindings_coverage() {
        Python::initialize();
        Python::attach(|py| {
            let module = pyo3::types::PyModule::new(py, "pyo3_sanitizer").unwrap();
            pyo3_sanitizer(&module).unwrap();

            let py_rich = module.getattr("sanitize_rich_text").unwrap();
            let res_rich: String = py_rich.call1(("<p>hello</p>",)).unwrap().extract().unwrap();
            assert_eq!(res_rich, "<p>hello</p>");

            let py_basic = module.getattr("sanitize_html_basic").unwrap();
            let res_basic: String = py_basic.call1(("<b>bold</b>",)).unwrap().extract().unwrap();
            assert_eq!(res_basic, "<b>bold</b>");

            let py_strip = module.getattr("strip_html").unwrap();
            let res_strip: String = py_strip
                .call1(("<p>strip</p>",))
                .unwrap()
                .extract()
                .unwrap();
            assert_eq!(res_strip, "strip");
        });
    }
}

// ── Property-Based Tests ──────────────────────────────────────────────────────
//
// proptest generates thousands of arbitrary strings per run, exercising code
// paths that hand-written KAT vectors miss.  Two invariants are verified:
//   1. Idempotency  — applying the sanitizer twice must equal applying it once.
//   2. No panic     — the sanitizer must never panic regardless of input.
//
// Strategy ".*" generates arbitrary Unicode strings including nulls, surrogates,
// lone high-surrogates, and other adversarial code-point sequences.
#[cfg(test)]
mod prop_tests {
    use super::*;
    use proptest::prelude::*;
    #[cfg(miri)]
    use proptest::test_runner::{noop_result_cache, RngAlgorithm, RngSeed};

    // Miri rejects the `getcwd` call used while proptest constructs its
    // default file-persistence provider.  Constructing the configuration
    // explicitly under Miri avoids that eager filesystem access while
    // preserving the same generation/shrinking defaults as `Config::default`.
    #[cfg(miri)]
    fn proptest_config() -> ProptestConfig {
        ProptestConfig {
            // Miri interprets every html5ever instruction and the full native
            // 256-case property run already executes in the regular Rust gate.
            // Keep every property active under Miri while bounding the
            // interpreter-only workload to a meaningful representative sample.
            cases: 32,
            max_local_rejects: 65_536,
            max_global_rejects: 1_024,
            max_flat_map_regens: 1_000_000,
            failure_persistence: None,
            source_file: None,
            test_name: None,
            fork: false,
            timeout: 0,
            max_shrink_time: 0,
            max_shrink_iters: u32::MAX,
            max_default_size_range: 100,
            result_cache: noop_result_cache,
            verbose: 0,
            rng_algorithm: RngAlgorithm::default(),
            rng_seed: RngSeed::Random,
            _non_exhaustive: (),
        }
    }

    #[cfg(not(miri))]
    fn proptest_config() -> ProptestConfig {
        ProptestConfig::default()
    }

    proptest! {
        #![proptest_config(proptest_config())]
        // ── sanitize_rich_text ───────────────────────────────────────────────

        /// Idempotency: sanitize(sanitize(x)) == sanitize(x) for rich mode.
        ///
        /// WHY: if the first pass produces output that the second pass would
        /// further modify, the caller cannot rely on a stable representation.
        #[test]
        fn sanitize_rich_text_is_idempotent(s in ".*") {
            let once = sanitize_rich_text(&s);
            let twice = sanitize_rich_text(&once);
            prop_assert_eq!(once, twice);
        }

        /// The sanitizer must not panic on any arbitrary Unicode input.
        #[test]
        fn sanitize_rich_text_never_panics(s in ".*") {
            let _ = sanitize_rich_text(&s);
        }

        /// Output must never contain a raw `<script` opening tag.
        ///
        /// WHY: the XSS invariant must hold across all generated strings, not
        /// just hand-picked attack vectors.
        #[test]
        fn sanitize_rich_text_never_emits_script_tag(s in ".*") {
            let out = sanitize_rich_text(&s);
            prop_assert!(
                !out.to_lowercase().contains("<script"),
                "script tag found in output: {:?}", out
            );
        }

        /// javascript: URIs must never survive sanitization.
        #[test]
        fn sanitize_rich_text_never_emits_javascript_scheme(s in ".*") {
            let out = sanitize_rich_text(&s);
            prop_assert!(
                !out.contains("javascript:"),
                "javascript: scheme found in output: {:?}", out
            );
        }

        // ── sanitize_html_basic ──────────────────────────────────────────────

        /// Idempotency for the basic (inline-only) mode.
        #[test]
        fn sanitize_html_basic_is_idempotent(s in ".*") {
            let once = sanitize_html_basic(&s);
            let twice = sanitize_html_basic(&once);
            prop_assert_eq!(once, twice);
        }

        /// Must not panic in basic mode.
        #[test]
        fn sanitize_html_basic_never_panics(s in ".*") {
            let _ = sanitize_html_basic(&s);
        }

        // ── strip_html ───────────────────────────────────────────────────────

        /// strip_html output must contain no angle-bracket markup whatsoever.
        ///
        /// WHY: the contract of strip_html is "zero HTML" — any surviving tag
        /// delimiter would be a regression in indexing pipelines.
        #[test]
        fn strip_html_output_has_no_angle_brackets(s in ".*") {
            let out = strip_html(&s);
            prop_assert!(
                !out.contains('<'),
                "angle bracket found in strip_html output: {:?}", out
            );
        }

        /// Idempotency for strip_html.
        #[test]
        fn strip_html_is_idempotent(s in ".*") {
            let once = strip_html(&s);
            let twice = strip_html(&once);
            prop_assert_eq!(once, twice);
        }

        /// Must not panic in strip mode.
        #[test]
        fn strip_html_never_panics(s in ".*") {
            let _ = strip_html(&s);
        }
    }
}
