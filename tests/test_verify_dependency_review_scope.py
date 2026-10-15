import json
import ssl
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "quality"))

from verify_dependency_review_scope import (
    CONFIG_PATH,
    EXPECTED_MODULES,
    EXPECTED_ROWS,
    LICENSE_REF,
    MAX_DEPENDENCY_COMPARE_BYTES,
    PURL_ADDITIONS,
    PURL_REMOVALS,
    _action_row,
    _git_show,
    _go_requirements,
    _has_tracked_replace,
    _identity,
    _open_dependency_request,
    expected_rows_for_delta,
    fetch_dependency_comparison,
    read_dependency_changes_file,
    verify_current_pins,
    verify_dependency_changes,
    verify_policy_delta,
    verify_policy_scope,
    write_dependency_changes_file,
)


def action_row(identity):
    change_type, manifest, ecosystem, name, version, purl, license_id = identity
    return {
        "change_type": change_type,
        "manifest": manifest,
        "ecosystem": ecosystem,
        "name": name,
        "version": version,
        "package_url": purl,
        "license": license_id,
        "source_repository_url": None,
        "vulnerabilities": [],
    }


def config(
    purls,
    license_ids=("MIT", "Apache-2.0", "BSD-3-Clause"),
    license_check="true",
    vuln_check="true",
):
    return (
        "fail-on-severity: high\n"
        "allow-licenses:\n"
        + "".join(f"  - {item}\n" for item in license_ids)
        + "allow-dependencies-licenses:\n"
        + "".join(f'  - "{item}"\n' for item in purls)
        + f"vulnerability-check: {vuln_check}\n"
        + f"license-check: {license_check}\n"
        + "comment-summary-in-pr: always\n"
    )


def current_mods(bad=None):
    result = {}
    for manifest, expected in EXPECTED_MODULES.items():
        lines = ["module example.test/module", "", "require ("]
        for name, version in expected.items():
            selected = "v9.9.9" if bad == (manifest, name) else version
            lines.append(f"    {name} {selected}")
        lines.append(")")
        result[manifest] = "\n".join(lines) + "\n"
    return result


class DependencyLicenseGuardTests(unittest.TestCase):
    def test_all_eight_exact_rows_pass(self):
        rows = [action_row(row) for row in EXPECTED_ROWS]
        self.assertEqual(verify_dependency_changes(rows, set(EXPECTED_ROWS)), 8)

    def test_exact_subset_passes_for_unrelated_pr(self):
        row = next(iter(EXPECTED_ROWS))
        self.assertEqual(verify_dependency_changes([action_row(row)], {row}), 1)

    def test_empty_array_passes_when_no_target_pin_changed(self):
        self.assertEqual(verify_dependency_changes("[]", set()), 0)

    def test_removed_rows_are_ignored(self):
        row = _identity(
            "services/gateway/go.mod",
            "github.com/klauspost/compress",
            "1.19.2",
            "BSD-3-Clause AND Apache-2.0 AND MIT",
        )
        row = ("removed", *row[1:])
        self.assertEqual(verify_dependency_changes([action_row(row)], set()), 0)

    def test_changed_version_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["version"] = "9.9.9"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_changed_manifest_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["manifest"] = "services/unknown/go.mod"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_changed_license_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["license"] = "Apache-2.0"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_changed_package_url_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["package_url"] = "pkg:golang/unknown@9.9.9"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_unknown_package_with_otel_marker_fails(self):
        row = action_row(
            _identity(
                "services/gateway/go.mod", "example.org/unknown", "1.0.0", LICENSE_REF
            )
        )
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_target_purl_with_mismatched_name_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["name"] = "example.org/unlisted"
        row["license"] = "Apache-2.0"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_target_purl_with_mismatched_ecosystem_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["ecosystem"] = "npm"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_target_name_with_mismatched_purl_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["package_url"] = "pkg:golang/example.org/unrelated@1.0.0"
        row["license"] = "Apache-2.0"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_percent_encoded_target_purl_cannot_bypass_guard(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        target_name = row["name"]
        target_version = row["version"]
        row["name"] = "example.org/unlisted"
        row["license"] = "Apache-2.0"
        row["package_url"] = (
            "pkg:golang/"
            + target_name.replace("/", "%2F")
            + "@"
            + target_version
            + "?type=module"
        )
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_new_target_purl_version_cannot_bypass_guard(self):
        row = action_row(
            next(row for row in EXPECTED_ROWS if "klauspost/compress" in row[3])
        )
        row["name"] = "example.org/unlisted"
        row["license"] = "Apache-2.0"
        row["version"] = "9.9.9"
        row["package_url"] = "pkg:golang/github.com%2Fklauspost%2Fcompress@9.9.9"
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_null_license_for_target_purl_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["name"] = "example.org/unlisted"
        row["license"] = None
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row])

    def test_duplicate_exact_row_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        with self.assertRaisesRegex(ValueError, "duplicate exact"):
            verify_dependency_changes([row, row])

    def test_missing_output_fails(self):
        with self.assertRaisesRegex(ValueError, "output is missing"):
            verify_dependency_changes(None)

    def test_empty_output_fails(self):
        with self.assertRaisesRegex(ValueError, "output is missing"):
            verify_dependency_changes("")

    def test_invalid_json_fails(self):
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            verify_dependency_changes("{")

    def test_non_array_json_fails(self):
        with self.assertRaisesRegex(ValueError, "JSON array"):
            verify_dependency_changes(json.dumps({"changes": []}))

    def test_pinned_action_required_schema_fields_are_checked(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        del row["source_repository_url"]
        with self.assertRaisesRegex(ValueError, "output schema"):
            _action_row(row)

    def test_action_schema_field_types_are_checked(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["ecosystem"] = None
        with self.assertRaisesRegex(ValueError, "required string"):
            _action_row(row)

    def test_action_schema_optional_scope_is_checked(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["scope"] = "other"
        with self.assertRaisesRegex(ValueError, "invalid scope"):
            _action_row(row)

    def test_unknown_change_type_fails(self):
        row = action_row(next(iter(EXPECTED_ROWS)))
        row["change_type"] = "changed"
        with self.assertRaisesRegex(ValueError, "unknown change_type"):
            verify_dependency_changes([row])

    def test_missing_required_changed_row_fails(self):
        rows = [action_row(row) for row in EXPECTED_ROWS]
        rows.pop()
        with self.assertRaisesRegex(ValueError, "omitted a changed"):
            verify_dependency_changes(rows, set(EXPECTED_ROWS))

    def test_runtime_policy_scope_requires_exact_unversioned_targets(self):
        values = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_scope(config(values))

    def test_runtime_policy_scope_rejects_versioned_target_purl(self):
        values = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        values.append("pkg:golang/github.com/klauspost/compress@1.20.1")
        with self.assertRaisesRegex(ValueError, "versioned target PURL"):
            verify_policy_scope(config(values))

    def test_runtime_policy_scope_rejects_global_license_ref(self):
        values = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        cfg = config(
            values, license_ids=("MIT", "LicenseRef-bad-apache-2.0-bsd-3-clause")
        )
        with self.assertRaisesRegex(ValueError, "global allow-licenses"):
            verify_policy_scope(cfg)

    def test_policy_delta_is_finite_and_preserves_other_lists(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_delta(config(old), config(new))

    def test_policy_delta_allows_prior_tightening_removals(self):
        old = [
            "pkg:npm/preserved",
            "pkg:pypi/portalocker",
            "pkg:pypi/qdrant-client",
            *PURL_REMOVALS.keys(),
        ]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_delta(config(old), config(new))

    def test_policy_delta_stays_valid_after_target_purls_merge(self):
        values = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_delta(config(values), config(values))

    def test_extra_package_exception_fails(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys(), "pkg:npm/extra"]
        with self.assertRaisesRegex(ValueError, "PURL additions"):
            verify_policy_delta(config(old), config(new))

    def test_global_allow_licenses_cannot_change(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        with self.assertRaisesRegex(ValueError, "policy list changed"):
            verify_policy_delta(
                config(old), config(new, license_ids=("MIT", "Apache-2.0"))
            )

    def test_license_and_vulnerability_checks_must_stay_enabled(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        with self.assertRaisesRegex(ValueError, "must remain enabled"):
            verify_policy_delta(config(old), config(new, vuln_check="false"))

    def test_exact_module_pins_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in current_mods().items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            self.assertEqual(len(verify_current_pins(root)), 8)

    def test_tracked_module_replace_fails_closed(self):
        content = current_mods()
        manifest = "services/gateway/go.mod"
        content[manifest] = (
            "replace github.com/klauspost/compress => example.test/fork v1.0.0\n"
            + content[manifest]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path, text in content.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "replaces a tracked"):
                verify_current_pins(root)

    def test_workspace_single_replace_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in current_mods().items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            (root / "go.work").write_text(
                "go 1.26.4\nreplace github.com/klauspost/compress => ../compress-fork\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "go.work replaces"):
                verify_current_pins(root)

    def test_workspace_block_replace_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in current_mods().items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            (root / "go.work").write_text(
                "go 1.26.4\nreplace (\n github.com/klauspost/compress v1.20.1 => ../compress-fork\n)\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "go.work replaces"):
                verify_current_pins(root)

    def test_go_mod_replace_lexer_covers_tabs_no_space_and_quoted_paths(self):
        cases = (
            "replace\tgithub.com/klauspost/compress\t=>\t../compress-fork\n",
            "replace(\n github.com/klauspost/compress v1.20.1 => ../compress-fork\n)\n",
            'replace "github.com/klauspost/compress" => "example.test/fork" v1.0.0\n',
            "replace (\n `github.com/klauspost/compress` v1.20.1 => ../compress-fork\n)\n",
        )
        for replacement in cases:
            with self.subTest(replacement=replacement):
                content = current_mods()
                manifest = "services/gateway/go.mod"
                content[manifest] = replacement + content[manifest]
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for path, text in content.items():
                        target = root / path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "replaces a tracked"):
                        verify_current_pins(root)

    def test_go_work_replace_lexer_covers_tabs_no_space_and_quoted_paths(self):
        cases = (
            "replace\tgithub.com/klauspost/compress\t=>\t../compress-fork\n",
            "replace(\n github.com/klauspost/compress v1.20.1 => ../compress-fork\n)\n",
            'replace "github.com/klauspost/compress" => example.test/fork v1.0.0\n',
            "replace (\n `github.com/klauspost/compress` => example.test/fork v1.0.0\n)\n",
        )
        for replacement in cases:
            with self.subTest(replacement=replacement):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for manifest, text in current_mods().items():
                        path = root / manifest
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(text, encoding="utf-8")
                    (root / "go.work").write_text(
                        "go 1.26.4\n" + replacement, encoding="utf-8"
                    )
                    with self.assertRaisesRegex(ValueError, "go.work replaces"):
                        verify_current_pins(root)

    def test_valid_non_target_replacements_remain_allowed(self):
        content = current_mods()
        content["services/gateway/go.mod"] = (
            "replace example.test/other => example.test/fork v1.0.0\n"
            + content["services/gateway/go.mod"]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in content.items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            (root / "go.work").write_text(
                "go 1.26.4\nreplace (\n example.test/elsewhere => example.test/fork v1.2.3\n)\n",
                encoding="utf-8",
            )
            self.assertEqual(len(verify_current_pins(root)), 8)

    def test_malformed_replace_directive_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "cannot parse Go replace directive"):
            _has_tracked_replace(
                "replace\tgithub.com/klauspost/compress\n",
                {"github.com/klauspost/compress"},
            )

    def test_changed_klauspost_pin_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in current_mods(
                ("services/ws-hub/go.mod", "github.com/klauspost/compress")
            ).items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must pin"):
                verify_current_pins(root)

    def test_base_pin_delta_requires_exact_rows(self):
        current = {
            (m, n): v.lstrip("v")
            for m, mods in EXPECTED_MODULES.items()
            for n, v in mods.items()
        }
        base = dict(current)
        base[("services/file-processor/go.mod", "github.com/klauspost/compress")] = (
            "1.20.0"
        )
        base[("services/gateway/go.mod", "github.com/klauspost/compress")] = "1.19.2"
        base[("services/ws-hub/go.mod", "github.com/klauspost/compress")] = "1.20.0"
        for key in current:
            if "opentelemetry.io" in key[1]:
                base[key] = "0.71.0" if "contrib" in key[1] else "1.46.0"
        self.assertEqual(expected_rows_for_delta(base, current), set(EXPECTED_ROWS))

    def test_unchanged_target_pins_require_no_rows(self):
        current = {
            (m, n): v.lstrip("v")
            for m, mods in EXPECTED_MODULES.items()
            for n, v in mods.items()
        }
        self.assertEqual(expected_rows_for_delta(current, current), set())

    def test_go_mod_parser_ignores_replace_line(self):
        text = "module example.test\nreplace github.com/klauspost/compress => example.test/fork v9.9.9\nrequire (\n github.com/klauspost/compress v1.20.1 // indirect\n)\n"
        self.assertEqual(
            _go_requirements(text, {"github.com/klauspost/compress"})[
                "github.com/klauspost/compress"
            ],
            ["v1.20.1"],
        )


class DependencyCompareFileTests(unittest.TestCase):
    base_sha = "a" * 40
    head_sha = "b" * 40
    repository = "egorribun/university_ecosystem"

    class Response:
        def __init__(self, url, payload, link=None):
            self.url = url
            self.body = json.dumps(payload).encode("utf-8")
            self.headers = {"Link": link} if link else {}
            self.status = 200
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def geturl(self):
            return self.url

        def read(self, limit=-1):
            return self.body if limit < 0 else self.body[:limit]

        def close(self):
            self.closed = True

    def initial_url(self):
        return (
            "https://api.github.com/repos/"
            + self.repository
            + "/dependency-graph/compare/"
            + self.base_sha
            + "..."
            + self.head_sha
            + "?per_page=100"
        )

    def test_fetch_paginates_all_rows_with_fixed_refs_and_bearer_token(self):
        rows = [action_row(row) for row in sorted(EXPECTED_ROWS)]
        first_url = self.initial_url()
        next_url = (
            "https://api.github.com/repositories/12345/dependency-graph/compare/"
            + self.base_sha
            + "..."
            + self.head_sha
            + "?per_page=100&page=2"
        )
        responses = [
            self.Response(
                first_url,
                rows[:4],
                f'<{next_url}>; rel="next", <{next_url}>; rel="last"',
            ),
            self.Response(next_url, rows[4:]),
        ]
        with patch(
            "verify_dependency_review_scope._open_dependency_request",
            side_effect=responses,
        ) as open_request:
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )
        self.assertEqual(actual, rows)
        self.assertEqual(open_request.call_count, 2)
        first_request = open_request.call_args_list[0].args
        self.assertEqual(first_request[0], first_url)
        self.assertEqual(first_request[1]["Authorization"], "Bearer test-only-token")

    def test_request_rejects_invalid_path_and_query_before_opening_opener(self):
        valid_url = self.initial_url()
        invalid_urls = (
            (
                valid_url.replace("/dependency-graph/compare/", "/contents/"),
                "request path is invalid",
            ),
            (valid_url + "&unexpected=1", "request query is invalid"),
            (valid_url.replace("per_page=100", "per_page=5"), "page size is invalid"),
        )
        for url, message in invalid_urls:
            with (
                self.subTest(url=url),
                patch(
                    "verify_dependency_review_scope._build_dependency_opener"
                ) as build_opener,
            ):
                with self.assertRaisesRegex(ValueError, message):
                    _open_dependency_request(
                        url, {"Authorization": "Bearer test-only-token"}
                    )
                build_opener.assert_not_called()

    def test_request_uses_fixed_https_host_and_refuses_redirects(self):
        first_url = self.initial_url()
        redirect_body = BytesIO(b"redirect response body")
        http_error = HTTPError(
            first_url,
            302,
            "Found",
            {"Location": "https://example.invalid/collect"},
            redirect_body,
        )

        class RecordingSSLContext:
            def __init__(self, context):
                self.context = context
                self.alpn_protocols = None

            def set_alpn_protocols(self, protocols):
                self.alpn_protocols = protocols
                self.context.set_alpn_protocols(protocols)

            def __getattr__(self, name):
                return getattr(self.context, name)

        tls_context = RecordingSSLContext(ssl.create_default_context())
        with (
            patch(
                "verify_dependency_review_scope.ssl.create_default_context",
                return_value=tls_context,
            ),
            patch("verify_dependency_review_scope.build_opener") as build_opener,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = http_error
            with self.assertRaisesRegex(ValueError, "returned HTTP 302"):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )

        handlers = build_opener.call_args.args
        self.assertEqual(len(handlers), 3)
        proxy_handler, https_handler, redirect_handler = handlers
        self.assertEqual(proxy_handler.proxies, {})
        self.assertIs(https_handler._context, tls_context)
        self.assertEqual(tls_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(tls_context.check_hostname)
        self.assertEqual(tls_context.alpn_protocols, ["http/1.1"])
        self.assertIsNone(
            redirect_handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {"Location": "https://example.invalid/collect"},
                "https://example.invalid/collect",
            )
        )
        self.assertEqual(
            opener.addheaders,
            [
                ("Accept", "application/vnd.github+json"),
                ("Authorization", "Bearer test-only-token"),
                ("X-GitHub-Api-Version", "2022-11-28"),
                ("User-Agent", "university-ecosystem-dependency-scope-guard"),
            ],
        )
        opener.open.assert_called_once_with(first_url, timeout=30)
        self.assertTrue(redirect_body.closed)

    def test_fixed_host_response_reads_with_the_global_byte_bound(self):
        response = self.Response(self.initial_url(), [])
        response.read = Mock(return_value=b"[]")
        with patch("verify_dependency_review_scope.build_opener") as build_opener:
            opener = build_opener.return_value
            opener.open.return_value = response
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )

        self.assertEqual(actual, [])
        opener.open.assert_called_once_with(self.initial_url(), timeout=30)
        response.read.assert_called_once_with(MAX_DEPENDENCY_COMPARE_BYTES + 1)
        self.assertTrue(response.closed)

    def test_request_rejects_other_origin_and_sanitizes_transport_errors(self):
        with patch(
            "verify_dependency_review_scope._build_dependency_opener"
        ) as build_opener:
            with self.assertRaisesRegex(ValueError, "fixed GitHub API host"):
                _open_dependency_request(
                    "https://example.invalid/repos/owner/repo/dependency-graph/compare/"
                    + self.base_sha
                    + "..."
                    + self.head_sha
                    + "?per_page=100",
                    {"Authorization": "Bearer test-only-token"},
                )
            build_opener.assert_not_called()

        with patch("verify_dependency_review_scope.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = URLError(
                "Bearer test-only-token"
            )
            with self.assertRaisesRegex(
                ValueError, "Dependency graph compare request failed"
            ) as caught:
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )
        self.assertNotIn("test-only-token", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_pagination_query_rejects_a_smaller_page_size(self):
        first_url = self.initial_url()
        response = self.Response(
            first_url,
            [],
            "<https://api.github.com/repositories/12345/dependency-graph/compare/"
            + self.base_sha
            + "..."
            + self.head_sha
            + "?per_page=5&page=2>; rel=next",
        )
        with patch(
            "verify_dependency_review_scope._open_dependency_request",
            return_value=response,
        ) as open_request:
            with self.assertRaisesRegex(ValueError, "unexpected pagination query"):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )
        open_request.assert_called_once()

    def test_cross_host_pagination_link_fails_before_followup_request(self):
        first_url = self.initial_url()
        response = self.Response(
            first_url,
            [],
            "<https://example.invalid/dependency-graph/compare/"
            + self.base_sha
            + "..."
            + self.head_sha
            + "?per_page=100&page=2>; rel=next",
        )
        with patch(
            "verify_dependency_review_scope._open_dependency_request",
            return_value=response,
        ) as open_request:
            with self.assertRaisesRegex(ValueError, "unexpected pagination URL"):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )
        open_request.assert_called_once()

    def test_non_array_compare_response_fails_closed(self):
        response = self.Response(self.initial_url(), {"changes": []})
        with patch(
            "verify_dependency_review_scope._open_dependency_request",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "JSON array"):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )

    def test_file_round_trip_preserves_rows_and_requires_unique_output(self):
        rows = [action_row(row) for row in EXPECTED_ROWS]
        with tempfile.TemporaryDirectory() as tmp:
            path, byte_count = write_dependency_changes_file(rows, Path(tmp))
            self.assertEqual(path.name, "dependency-review-changes.json")
            self.assertEqual(path.stat().st_size, byte_count)
            loaded = read_dependency_changes_file(path)
            self.assertEqual(verify_dependency_changes(loaded, set(EXPECTED_ROWS)), 8)
            with self.assertRaisesRegex(ValueError, "already exists"):
                write_dependency_changes_file(rows, Path(tmp))

    def test_missing_invalid_and_nonstandard_json_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.json"
            with self.assertRaisesRegex(ValueError, "missing or unreadable"):
                read_dependency_changes_file(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                read_dependency_changes_file(path)
            path.write_text("[NaN]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                read_dependency_changes_file(path)

    def test_oversized_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changes.json"
            path.write_text("[]", encoding="utf-8")
            with patch(
                "verify_dependency_review_scope.MAX_DEPENDENCY_COMPARE_BYTES", 1
            ):
                with self.assertRaisesRegex(ValueError, "bounded regular file"):
                    read_dependency_changes_file(path)


class ProtectedBaseGitReadTests(unittest.TestCase):
    root = Path("private-repository")
    valid_sha = "a" * 40

    def test_invalid_ref_is_rejected_before_git(self):
        for ref in ("a" * 39, "g" * 40, "A" * 40):
            with (
                self.subTest(ref=ref),
                patch("verify_dependency_review_scope.subprocess.run") as run,
            ):
                with self.assertRaisesRegex(ValueError, "immutable SHA"):
                    _git_show(self.root, ref, CONFIG_PATH)
                run.assert_not_called()

    def test_unlisted_and_traversal_paths_are_rejected_before_git(self):
        for path in ("../.secrets.baseline", ".git/config", "services/../.git/config"):
            with (
                self.subTest(path=path),
                patch("verify_dependency_review_scope.subprocess.run") as run,
            ):
                with self.assertRaisesRegex(ValueError, "known manifest"):
                    _git_show(self.root, self.valid_sha, path)
                run.assert_not_called()

    def test_missing_git_executable_fails_closed(self):
        with (
            patch("verify_dependency_review_scope.shutil.which", return_value=None),
            patch("verify_dependency_review_scope.subprocess.run") as run,
        ):
            with self.assertRaisesRegex(ValueError, "Git executable is unavailable"):
                _git_show(self.root, self.valid_sha, CONFIG_PATH)
            run.assert_not_called()

    def test_git_call_uses_validated_arguments_and_bounded_timeout(self):
        expected_text = "license-check: true\n"
        with (
            patch(
                "verify_dependency_review_scope.shutil.which",
                return_value="C:/Git/cmd/git.exe",
            ),
            patch(
                "verify_dependency_review_scope.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0, stdout=expected_text.encode("utf-8")
                ),
            ) as run,
        ):
            self.assertEqual(
                _git_show(self.root, self.valid_sha, CONFIG_PATH), expected_text
            )
        args, kwargs = run.call_args
        self.assertEqual(
            args[0],
            ["C:/Git/cmd/git.exe", "show", f"{self.valid_sha}:{CONFIG_PATH}"],
        )
        self.assertEqual(kwargs["cwd"], self.root)
        self.assertTrue(kwargs["capture_output"])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 30)

    def test_nonzero_git_exit_fails_without_echoing_command_output(self):
        with (
            patch("verify_dependency_review_scope.shutil.which", return_value="git"),
            patch(
                "verify_dependency_review_scope.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=128, stdout=b"", stderr=b"private error detail"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError, "cannot read protected-base file"
            ) as error:
                _git_show(self.root, self.valid_sha, CONFIG_PATH)
            self.assertNotIn("private error detail", str(error.exception))

    def test_timeout_and_launch_errors_fail_closed(self):
        failures = (
            subprocess.TimeoutExpired("git", 30),
            OSError("git executable disappeared"),
        )
        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                patch(
                    "verify_dependency_review_scope.shutil.which", return_value="git"
                ),
                patch(
                    "verify_dependency_review_scope.subprocess.run",
                    side_effect=failure,
                ) as run,
            ):
                with self.assertRaises(type(failure)):
                    _git_show(self.root, self.valid_sha, CONFIG_PATH)
                self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_invalid_utf8_git_output_fails_closed(self):
        with (
            patch("verify_dependency_review_scope.shutil.which", return_value="git"),
            patch(
                "verify_dependency_review_scope.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=b"\xff"),
            ),
        ):
            with self.assertRaises(UnicodeDecodeError):
                _git_show(self.root, self.valid_sha, CONFIG_PATH)


if __name__ == "__main__":
    unittest.main()
