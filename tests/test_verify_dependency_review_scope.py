import hashlib
import io
import json
import ssl
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "quality"))

from scripts.quality.verify_dependency_review_scope import (
    CONFIG_PATH,
    EXPECTED_MODULES,
    EXPECTED_ROWS,
    GHSA_EXCEPTIONS,
    LICENSE_REF,
    MAX_DEPENDENCY_COMPARE_BYTES,
    PURL_ADDITIONS,
    PURL_REMOVALS,
    _action_row,
    _base_manifest_exists,
    _base_pins,
    _git_show,
    _go_requirements,
    _has_tracked_replace,
    _identity,
    _open_dependency_request,
    _parse_config,
    expected_rows_for_delta,
    fetch_dependency_comparison,
    main,
    preflight,
    read_dependency_changes_file,
    verify_current_pins,
    verify_dependency_changes,
    verify_ghsa_exception_rows,
    verify_policy_delta,
    verify_policy_scope,
    write_dependency_changes_file,
)

PINNED_MODULE_COUNT = sum(len(mods) for mods in EXPECTED_MODULES.values())


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
    ghsas=(),
):
    ghsa_section = (
        "allow-ghsas:\n" + "".join(f'  - "{item}"\n' for item in ghsas) if ghsas else ""
    )
    return (
        "fail-on-severity: high\n"
        "allow-licenses:\n"
        + "".join(f"  - {item}\n" for item in license_ids)
        + ghsa_section
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
    def test_all_exact_rows_pass(self):
        rows = [action_row(row) for row in EXPECTED_ROWS]
        self.assertEqual(
            verify_dependency_changes(rows, set(EXPECTED_ROWS)), len(EXPECTED_ROWS)
        )

    @staticmethod
    def _plist_identity(**changes):
        identity = next(row for row in EXPECTED_ROWS if row[3] == "howett.net/plist")
        fields = dict(
            zip(
                (
                    "change_type",
                    "manifest",
                    "ecosystem",
                    "name",
                    "version",
                    "purl",
                    "license",
                ),
                identity,
                strict=True,
            )
        )
        fields.update(changes)
        return (
            fields["change_type"],
            fields["manifest"],
            fields["ecosystem"],
            fields["name"],
            fields["version"],
            fields["purl"],
            fields["license"],
        )

    def test_caddy_plist_row_passes_only_at_its_reviewed_identity(self):
        identity = self._plist_identity()
        self.assertEqual(
            identity[1:5],
            ("services/caddy/go.mod", "gomod", "howett.net/plist", "1.0.1"),
        )
        self.assertEqual(identity[6], "BSD-2-Clause-Views AND BSD-3-Clause")
        self.assertEqual(
            verify_dependency_changes([action_row(identity)], {identity}), 1
        )

    def test_plist_other_version_manifest_or_license_fails(self):
        mutations = (
            {"version": "1.0.2", "purl": "pkg:golang/howett.net/plist@1.0.2"},
            {"manifest": "services/gateway/go.mod"},
            {"license": "BSD-3-Clause"},
            {"license": "LicenseRef-bad-bsd-2-clause-views-bsd-3-clause"},
            {"license": "BSD-2-Clause AND BSD-3-Clause"},
            {"license": "BSD-3-Clause AND BSD-2-Clause-Views"},
            {"license": "BSD-2-Clause-Views OR BSD-3-Clause"},
            {"license": "BSD-2-Clause-Views AND BSD-3-Clause "},
            {"license": None},
        )
        for changes in mutations:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "unexpected package"):
                    verify_dependency_changes(
                        [action_row(self._plist_identity(**changes))], set()
                    )

    def test_reviewed_plist_row_is_required_when_its_pin_changes(self):
        identity = self._plist_identity()
        with self.assertRaisesRegex(ValueError, "omitted a changed reviewed"):
            verify_dependency_changes([], {identity})

    def test_name_only_plist_exception_is_required_and_not_versioned(self):
        purls = [item for item in PURL_ADDITIONS if "howett.net/plist" not in item]
        with self.assertRaisesRegex(ValueError, "exact package-name PURL"):
            verify_policy_scope(config(purls))
        with self.assertRaisesRegex(ValueError, "versioned target PURL"):
            verify_policy_scope(
                config([*PURL_ADDITIONS, "pkg:golang/howett.net/plist@1.0.1"])
            )

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

    def test_repository_config_ghsa_entries_are_bounded_exceptions(self):
        # AUD-479: every allowed GHSA must have a scoped, owned, expiring record.
        config_path = Path(__file__).parents[1] / CONFIG_PATH
        config_text = config_path.read_text(encoding="utf-8")
        _scalars, sections = _parse_config(config_text)
        self.assertEqual(
            sorted(sections.get("allow-ghsas", [])),
            sorted(record["ghsa"] for record in GHSA_EXCEPTIONS),
        )
        verify_policy_scope(config_text, today=date(2026, 11, 2))

    def test_policy_scope_rejects_a_global_ghsa_suppression(self):
        purls = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        with self.assertRaisesRegex(ValueError, "global GHSA allowlist"):
            verify_policy_scope(config(purls, ghsas=("GHSA-4c8g-83qw-93j6",)))

    def test_policy_delta_allows_ghsa_suppression_removals(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        base_text = config(
            old,
            ghsas=("GHSA-4c8g-83qw-93j6", "GHSA-v2hh-gcrm-f6hx"),
        )
        current_text = config(new)
        verify_policy_delta(base_text, current_text)

    def test_policy_delta_rejects_ghsa_suppression_additions(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        base_text = config(old)
        current_text = config(new, ghsas=("GHSA-4c8g-83qw-93j6",))
        with self.assertRaisesRegex(ValueError, "GHSA allowlist additions"):
            verify_policy_delta(base_text, current_text)

    def test_exact_module_pins_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for manifest, text in current_mods().items():
                path = root / manifest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            self.assertEqual(len(verify_current_pins(root)), PINNED_MODULE_COUNT)

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
            self.assertEqual(len(verify_current_pins(root)), PINNED_MODULE_COUNT)

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
        # The caddy manifest is new relative to the base, so none of its pins
        # exist there and all three of its reviewed rows are required.
        for key in current:
            if key[0] == "services/caddy/go.mod":
                base[key] = None
        self.assertEqual(expected_rows_for_delta(base, current), set(EXPECTED_ROWS))

    def test_caddy_pins_unchanged_from_base_require_no_rows(self):
        current = {
            (m, n): v.lstrip("v")
            for m, mods in EXPECTED_MODULES.items()
            for n, v in mods.items()
        }
        base = dict(current)
        self.assertEqual(expected_rows_for_delta(base, current), set())

    def test_manifest_absent_at_base_requires_every_pin(self):
        module = "scripts.quality.verify_dependency_review_scope"
        caddy = "services/caddy/go.mod"
        with (
            patch(
                f"{module}._base_manifest_exists",
                side_effect=lambda _root, _sha, manifest: manifest != caddy,
            ),
            patch(f"{module}._git_show", return_value="module example.test\n"),
        ):
            base = _base_pins(Path("."), "0" * 40)
        caddy_keys = {key for key in base if key[0] == caddy}
        self.assertEqual(
            caddy_keys, {(caddy, name) for name in EXPECTED_MODULES[caddy]}
        )
        self.assertTrue(all(base[key] is None for key in caddy_keys))

    def test_base_manifest_lookup_distinguishes_absent_from_git_failure(self):
        module = "scripts.quality.verify_dependency_review_scope"
        manifest = "services/caddy/go.mod"
        for stdout, expected in ((b"services/caddy/go.mod\n", True), (b"", False)):
            with (
                patch(
                    f"{module}.shutil.which",
                    return_value="C:/Git/cmd/git.exe",
                ),
                patch(
                    f"{module}.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout=stdout),
                ) as run,
            ):
                self.assertIs(
                    _base_manifest_exists(Path("."), "0" * 40, manifest), expected
                )
            args = run.call_args.args[0]
            self.assertEqual(args[1:3], ["ls-tree", "--full-tree"])
            self.assertEqual(args[-2:], ["--", manifest])
        with (
            patch(f"{module}.shutil.which", return_value="C:/Git/cmd/git.exe"),
            patch(
                f"{module}.subprocess.run",
                return_value=SimpleNamespace(returncode=128, stdout=b""),
            ),
            self.assertRaisesRegex(ValueError, "cannot read protected-base tree"),
        ):
            _base_manifest_exists(Path("."), "0" * 40, manifest)
        with self.assertRaisesRegex(ValueError, "immutable SHA"):
            _base_manifest_exists(Path("."), "main", manifest)
        with self.assertRaisesRegex(ValueError, "immutable SHA"):
            _base_manifest_exists(Path("."), "0" * 40, "services/unknown/go.mod")

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

    def http_error(self, status, retry_after=None):
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        body = BytesIO(b"Bearer test-only-token")
        return HTTPError(
            self.initial_url(), status, "temporary response", headers, body
        ), body

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
            "scripts.quality.verify_dependency_review_scope._open_dependency_request",
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

    def test_transient_502_retries_then_succeeds_and_closes_both_responses(self):
        error, error_body = self.http_error(502, retry_after="30")
        response = self.Response(self.initial_url(), [])
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = [error, response]
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )

        self.assertEqual(actual, [])
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(2.0)
        self.assertTrue(error_body.closed)
        self.assertTrue(response.closed)

    def test_transient_429_retries_and_retry_after_is_bounded(self):
        error, error_body = self.http_error(429, retry_after="999999")
        response = self.Response(self.initial_url(), [])
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = [error, response]
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )

        self.assertEqual(actual, [])
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(2.0)
        self.assertTrue(error_body.closed)
        self.assertTrue(response.closed)

    def test_transient_504_retries_with_bounded_backoff(self):
        error, error_body = self.http_error(504)
        response = self.Response(self.initial_url(), [])
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = [error, response]
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )

        self.assertEqual(actual, [])
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(0.25)
        self.assertTrue(error_body.closed)
        self.assertTrue(response.closed)

    def test_transient_http_exhaustion_fails_closed_without_reusing_responses(self):
        errors_and_bodies = [self.http_error(503, retry_after="0") for _ in range(4)]
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = [error for error, _ in errors_and_bodies]
            with self.assertRaisesRegex(ValueError, "returned HTTP 503") as caught:
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )

        self.assertEqual(opener.open.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(0.0,)] * 3)
        self.assertNotIn("test-only-token", str(caught.exception))
        self.assertTrue(all(body.closed for _, body in errors_and_bodies))

    def test_forbidden_status_is_not_retried_and_error_is_sanitized(self):
        error, error_body = self.http_error(403)
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = error
            with self.assertRaisesRegex(ValueError, "returned HTTP 403") as caught:
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )

        opener.open.assert_called_once()
        sleep.assert_not_called()
        self.assertTrue(error_body.closed)
        self.assertNotIn("test-only-token", str(caught.exception))

    def test_malformed_success_response_is_not_retried(self):
        response = self.Response(self.initial_url(), [])
        response.body = b"{invalid"
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.return_value = response
            with self.assertRaisesRegex(ValueError, "returned invalid JSON"):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )

        opener.open.assert_called_once()
        sleep.assert_not_called()
        self.assertTrue(response.closed)

    def test_explicit_network_timeout_is_retried(self):
        response = self.Response(self.initial_url(), [])
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
            patch("scripts.quality.verify_dependency_review_scope.time.sleep") as sleep,
        ):
            opener = build_opener.return_value
            opener.open.side_effect = [URLError(TimeoutError("timed out")), response]
            actual = fetch_dependency_comparison(
                self.repository, self.base_sha, self.head_sha, "test-only-token"
            )

        self.assertEqual(actual, [])
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(0.25)
        self.assertTrue(response.closed)

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
                    "scripts.quality.verify_dependency_review_scope._build_dependency_opener"
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
                "scripts.quality.verify_dependency_review_scope.ssl.create_default_context",
                return_value=tls_context,
            ),
            patch(
                "scripts.quality.verify_dependency_review_scope.build_opener"
            ) as build_opener,
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
        with patch(
            "scripts.quality.verify_dependency_review_scope.build_opener"
        ) as build_opener:
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
            "scripts.quality.verify_dependency_review_scope._build_dependency_opener"
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

        with patch(
            "scripts.quality.verify_dependency_review_scope.build_opener"
        ) as build_opener:
            build_opener.return_value.open.side_effect = URLError(
                "Bearer test-only-token"
            )
            with (
                patch(
                    "scripts.quality.verify_dependency_review_scope.time.sleep"
                ) as sleep,
                self.assertRaisesRegex(
                    ValueError, "Dependency graph compare request failed"
                ) as caught,
            ):
                fetch_dependency_comparison(
                    self.repository, self.base_sha, self.head_sha, "test-only-token"
                )
            build_dependency_opener = build_opener.return_value
            build_dependency_opener.open.assert_called_once()
            sleep.assert_not_called()
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
            "scripts.quality.verify_dependency_review_scope._open_dependency_request",
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
            "scripts.quality.verify_dependency_review_scope._open_dependency_request",
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
            "scripts.quality.verify_dependency_review_scope._open_dependency_request",
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
            self.assertEqual(
                verify_dependency_changes(loaded, set(EXPECTED_ROWS)),
                len(EXPECTED_ROWS),
            )
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
                "scripts.quality.verify_dependency_review_scope.MAX_DEPENDENCY_COMPARE_BYTES",
                1,
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
                patch(
                    "scripts.quality.verify_dependency_review_scope.subprocess.run"
                ) as run,
            ):
                with self.assertRaisesRegex(ValueError, "immutable SHA"):
                    _git_show(self.root, ref, CONFIG_PATH)
                run.assert_not_called()

    def test_unlisted_and_traversal_paths_are_rejected_before_git(self):
        for path in ("../.secrets.baseline", ".git/config", "services/../.git/config"):
            with (
                self.subTest(path=path),
                patch(
                    "scripts.quality.verify_dependency_review_scope.subprocess.run"
                ) as run,
            ):
                with self.assertRaisesRegex(ValueError, "known manifest"):
                    _git_show(self.root, self.valid_sha, path)
                run.assert_not_called()

    def test_missing_git_executable_fails_closed(self):
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.shutil.which",
                return_value=None,
            ),
            patch(
                "scripts.quality.verify_dependency_review_scope.subprocess.run"
            ) as run,
        ):
            with self.assertRaisesRegex(ValueError, "Git executable is unavailable"):
                _git_show(self.root, self.valid_sha, CONFIG_PATH)
            run.assert_not_called()

    def test_git_call_uses_validated_arguments_and_bounded_timeout(self):
        expected_text = "license-check: true\n"
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.shutil.which",
                return_value="C:/Git/cmd/git.exe",
            ),
            patch(
                "scripts.quality.verify_dependency_review_scope.subprocess.run",
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
            patch(
                "scripts.quality.verify_dependency_review_scope.shutil.which",
                return_value="git",
            ),
            patch(
                "scripts.quality.verify_dependency_review_scope.subprocess.run",
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
                    "scripts.quality.verify_dependency_review_scope.shutil.which",
                    return_value="git",
                ),
                patch(
                    "scripts.quality.verify_dependency_review_scope.subprocess.run",
                    side_effect=failure,
                ) as run,
            ):
                with self.assertRaises(type(failure)):
                    _git_show(self.root, self.valid_sha, CONFIG_PATH)
                self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_invalid_utf8_git_output_fails_closed(self):
        with (
            patch(
                "scripts.quality.verify_dependency_review_scope.shutil.which",
                return_value="git",
            ),
            patch(
                "scripts.quality.verify_dependency_review_scope.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=b"\xff"),
            ),
        ):
            with self.assertRaises(UnicodeDecodeError):
                _git_show(self.root, self.valid_sha, CONFIG_PATH)


def _advisory_row(manifest, name, version, ghsa, change_type="added"):
    vulnerabilities = []
    if ghsa:
        vulnerabilities.append(
            {
                "severity": "high",
                "advisory_ghsa_id": ghsa,
                "advisory_summary": "Go JOSE: DoS when parsing JWKs that contain RSA keys",
                "advisory_url": f"https://github.com/advisories/{ghsa}",
            }
        )
    return {
        "change_type": change_type,
        "manifest": manifest,
        "ecosystem": "gomod",
        "name": name,
        "version": version,
        "package_url": f"pkg:golang/{name}@{version}",
        "license": "Apache-2.0 AND BSD-3-Clause",
        "source_repository_url": None,
        "vulnerabilities": vulnerabilities,
    }


CADDY_JOSE_GHSA = "GHSA-mgcc-cww5-fp2q"
CADDY_JOSE_ROW = _advisory_row(
    "services/caddy/go.mod", "github.com/go-jose/go-jose/v3", "3.0.5", CADDY_JOSE_GHSA
)


class GhsaBoundedExceptionTests(unittest.TestCase):
    """AUD-479: the GHSA exception is bounded to one manifest, package and version."""

    def test_exception_is_recorded_with_owner_expiry_and_scope(self):
        record = GHSA_EXCEPTIONS[0]
        self.assertEqual(record["ghsa"], CADDY_JOSE_GHSA)
        self.assertEqual(record["owner"], "egorribun")
        self.assertEqual(record["expires"], date(2027, 1, 10))
        self.assertEqual(record["manifest"], "services/caddy/go.mod")
        self.assertEqual(record["ecosystem"], "gomod")
        self.assertEqual(record["name"], "github.com/go-jose/go-jose/v3")
        self.assertEqual(record["version"], "3.0.5")
        self.assertTrue(record["reason"].strip())
        self.assertTrue(record["reachability"].strip())

    def test_exact_caddy_manifest_row_is_accepted_under_exception(self):
        self.assertEqual(
            verify_ghsa_exception_rows([CADDY_JOSE_ROW], today=date(2026, 11, 2)),
            1,
        )

    def test_same_ghsa_in_another_manifest_fails(self):
        row = _advisory_row(
            "services/gateway/go.mod",
            "github.com/go-jose/go-jose/v3",
            "3.0.5",
            CADDY_JOSE_GHSA,
        )
        with self.assertRaisesRegex(ValueError, "outside its reviewed"):
            verify_ghsa_exception_rows([row], today=date(2026, 11, 2))

    def test_same_ghsa_for_another_package_or_version_fails(self):
        other_version = _advisory_row(
            "services/caddy/go.mod",
            "github.com/go-jose/go-jose/v3",
            "3.0.6",
            CADDY_JOSE_GHSA,
        )
        other_package = _advisory_row(
            "services/caddy/go.mod",
            "github.com/go-jose/go-jose/v4",
            "3.0.5",
            CADDY_JOSE_GHSA,
        )
        for row in (other_version, other_package):
            with self.subTest(package_url=row["package_url"]):
                with self.assertRaisesRegex(ValueError, "outside its reviewed"):
                    verify_ghsa_exception_rows([row], today=date(2026, 11, 2))

    def test_exception_fails_on_and_after_expiry_date(self):
        for day in (date(2027, 1, 10), date(2027, 2, 1)):
            with self.subTest(day=day.isoformat()):
                with self.assertRaisesRegex(ValueError, "expired"):
                    verify_ghsa_exception_rows([CADDY_JOSE_ROW], today=day)

    def test_exception_still_passes_the_day_before_expiry(self):
        self.assertEqual(
            verify_ghsa_exception_rows([CADDY_JOSE_ROW], today=date(2027, 1, 9)),
            1,
        )

    def test_removed_rows_and_clean_rows_are_not_counted(self):
        removed = _advisory_row(
            "services/gateway/go.mod",
            "github.com/go-jose/go-jose/v3",
            "3.0.5",
            CADDY_JOSE_GHSA,
            change_type="removed",
        )
        clean = _advisory_row(
            "services/caddy/go.mod", "github.com/go-jose/go-jose/v3", "3.0.5", None
        )
        self.assertEqual(
            verify_ghsa_exception_rows([removed, clean], today=date(2026, 11, 2)),
            0,
        )

    def test_malformed_exception_records_fail_closed(self):
        base = dict(GHSA_EXCEPTIONS[0])
        malformed = {
            "missing owner": {k: v for k, v in base.items() if k != "owner"},
            "wildcard manifest": {**base, "manifest": "services/*/go.mod"},
            "string expiry": {**base, "expires": "2027-01-10"},
            "invalid advisory id": {**base, "ghsa": "GHSA-short"},
            "unknown field": {**base, "global": True},
        }
        for label, record in malformed.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    verify_ghsa_exception_rows(
                        [CADDY_JOSE_ROW],
                        today=date(2026, 11, 2),
                        exceptions=[record],
                    )

    def test_policy_scope_accepts_only_the_bounded_config_entry(self):
        purls = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_scope(
            config(purls, ghsas=(CADDY_JOSE_GHSA,)), today=date(2026, 11, 2)
        )

    def test_policy_scope_rejects_expired_config_entry_on_expiry_date(self):
        purls = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_policy_scope(
                config(purls, ghsas=(CADDY_JOSE_GHSA,)), today=date(2027, 1, 10)
            )

    def test_policy_delta_allows_only_the_recorded_ghsa_addition(self):
        old = ["pkg:npm/preserved", *PURL_REMOVALS.keys()]
        new = ["pkg:npm/preserved", *PURL_ADDITIONS.keys()]
        verify_policy_delta(config(old), config(new, ghsas=(CADDY_JOSE_GHSA,)))
        with self.assertRaisesRegex(ValueError, "GHSA allowlist additions"):
            verify_policy_delta(
                config(old),
                config(new, ghsas=(CADDY_JOSE_GHSA, "GHSA-4c8g-83qw-93j6")),
            )

    def test_non_mapping_exception_record_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete or has unknown fields"):
            verify_ghsa_exception_rows(
                [CADDY_JOSE_ROW],
                today=date(2026, 11, 2),
                exceptions=["GHSA-mgcc-cww5-fp2q"],
            )

    def test_duplicate_exception_record_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate GHSA exception record"):
            verify_ghsa_exception_rows(
                [CADDY_JOSE_ROW],
                today=date(2026, 11, 2),
                exceptions=[GHSA_EXCEPTIONS[0], GHSA_EXCEPTIONS[0]],
            )

    def test_empty_exception_reason_fails_closed(self):
        record = {**GHSA_EXCEPTIONS[0], "reason": "   "}
        with self.assertRaisesRegex(ValueError, "invalid reason"):
            verify_ghsa_exception_rows(
                [CADDY_JOSE_ROW],
                today=date(2026, 11, 2),
                exceptions=[record],
            )

    def test_malformed_vulnerability_entry_fails_closed(self):
        row = _advisory_row("services/caddy/go.mod", "github.com/x/y", "1.0.0", None)
        row["vulnerabilities"] = ["GHSA-mgcc-cww5-fp2q"]
        with self.assertRaisesRegex(ValueError, "invalid vulnerability entry"):
            verify_ghsa_exception_rows([row], today=date(2026, 11, 2))

    def test_default_date_scans_rows_without_recorded_advisories(self):
        clean = _advisory_row("services/caddy/go.mod", "github.com/x/y", "1.0.0", None)
        self.assertEqual(verify_ghsa_exception_rows([clean]), 0)

    def test_unrecorded_advisory_on_a_scoped_row_is_not_counted(self):
        row = _advisory_row(
            "services/caddy/go.mod",
            "github.com/go-jose/go-jose/v3",
            "3.0.5",
            "GHSA-4c8g-83qw-93j6",
        )
        self.assertEqual(verify_ghsa_exception_rows([row], today=date(2026, 11, 2)), 0)

    def test_vulnerability_without_an_advisory_id_is_not_counted(self):
        row = _advisory_row("services/caddy/go.mod", "github.com/x/y", "1.0.0", None)
        row["vulnerabilities"] = [{"severity": "high"}]
        self.assertEqual(verify_ghsa_exception_rows([row], today=date(2026, 11, 2)), 0)

    def test_preflight_passes_the_supplied_date_to_the_policy_scope(self):
        root = Path(__file__).parents[1]
        module = "scripts.quality.verify_dependency_review_scope"
        with (
            patch(f"{module}.verify_current_pins", return_value={}),
            patch(f"{module}._git_show", return_value=""),
            patch(f"{module}.verify_policy_delta"),
            patch(f"{module}._base_pins", return_value={}),
            patch(f"{module}.expected_rows_for_delta", return_value=set()),
            patch(f"{module}.verify_policy_scope") as scope,
        ):
            preflight(root, "0" * 40, today=date(2026, 11, 2))
        scope.assert_called_once()
        self.assertEqual(scope.call_args.kwargs["today"], date(2026, 11, 2))

    def test_changes_phase_reports_the_bounded_exception_use(self):
        module = "scripts.quality.verify_dependency_review_scope"
        argv = [
            "verify",
            "changes",
            "--base-sha",
            "0" * 40,
            "--changes-file",
            "changes.json",
        ]
        with (
            patch(f"{module}.preflight", return_value=set()),
            patch(
                f"{module}.read_dependency_changes_file", return_value=[CADDY_JOSE_ROW]
            ),
            patch.object(sys, "argv", argv),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(main(), 0)
        self.assertIn("ghsa_exceptions_used=1", output.getvalue())


class DependencyIdentityDiagnosticTests(unittest.TestCase):
    @staticmethod
    def rows():
        return [
            action_row(
                (
                    "added",
                    ".github/workflows/trufflehog.yml",
                    "actions",
                    "trufflesecurity/trufflehog",
                    "a" * 40,  # Synthetic low-entropy pin, not a production SHA.
                    "pkg:github/trufflesecurity/trufflehog@" + "a" * 40,
                    "AGPL-3.0",
                )
            ),
            action_row(
                (
                    "added",
                    "services/caddy/go.mod",
                    "gomod",
                    "howett.net/plist",
                    "1.0.1",
                    "pkg:golang/howett.net/plist@1.0.1",
                    "BSD-2-Clause-Views AND BSD-3-Clause",
                )
            ),
            action_row(
                (
                    "added",
                    "services/caddy/go.mod",
                    "gomod",
                    "github.com/klauspost/compress",
                    "1.20.1",
                    "pkg:golang/github.com/klauspost/compress@1.20.1",
                    "BSD-3-Clause AND Apache-2.0 AND MIT",
                )
            ),
            action_row(
                (
                    "added",
                    "services/caddy/go.mod",
                    "gomod",
                    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
                    "1.46.0",
                    "pkg:golang/go.opentelemetry.io/otel/exporters/otlp/"
                    "otlptrace/otlptracegrpc@1.46.0",
                    "Apache-2.0 AND BSD-3-Clause",
                )
            ),
        ]

    def render(self, rows):
        module = sys.modules[verify_dependency_changes.__module__]
        formatter = getattr(module, "format_dependency_identity_diagnostics", None)
        self.assertTrue(callable(formatter), "bounded identity diagnostics missing")
        return formatter(rows)

    def test_only_seven_identity_fields_are_emitted_for_four_target_names(self):
        rows = self.rows()
        for row in rows:
            row["source_repository_url"] = "withheld-source-canary"
            row["vulnerabilities"] = [{"private": "withheld-advisory-canary"}]
            row["extra"] = "withheld-extra-canary"
        rows.append(
            action_row(
                (
                    "added",
                    "withheld-manifest-canary",
                    "npm",
                    "withheld-package-canary",
                    "withheld-version-canary",
                    "withheld-purl-canary",
                    "withheld-license-canary",
                )
            )
        )
        encoded = self.render(rows)
        payload = json.loads(encoded)
        self.assertEqual(payload["diagnostic"], "dependency-review-identities-v1")
        self.assertFalse(payload["truncated"])
        self.assertEqual(len(payload["rows"]), 4)
        expected_fields = {
            "change_type",
            "manifest",
            "ecosystem",
            "name",
            "version",
            "package_url",
            "license",
        }
        for row in payload["rows"]:
            self.assertEqual(set(row), expected_fields)
        by_name = {row["name"]: row for row in payload["rows"]}
        self.assertEqual(
            by_name["howett.net/plist"],
            {
                "change_type": "added",
                "manifest": "services/caddy/go.mod",
                "ecosystem": "gomod",
                "name": "howett.net/plist",
                "version": "1.0.1",
                "package_url": "pkg:golang/howett.net/plist@1.0.1",
                "license": "BSD-2-Clause-Views AND BSD-3-Clause",
            },
        )
        self.assertEqual(
            by_name["trufflesecurity/trufflehog"]["version"],
            "<redacted>",
        )
        self.assertEqual(
            by_name["trufflesecurity/trufflehog"]["package_url"],
            "<matches-40-hex-version>",
        )
        self.assertNotIn("a" * 40, encoded)
        self.assertEqual(
            by_name["github.com/klauspost/compress"]["license"],
            "BSD-3-Clause AND Apache-2.0 AND MIT",
        )
        self.assertEqual(
            by_name["go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"][
                "package_url"
            ],
            "pkg:golang/go.opentelemetry.io/otel/exporters/otlp/"
            "otlptrace/otlptracegrpc@1.46.0",
        )
        self.assertNotIn("withheld-", encoded)
        self.assertNotIn("source_repository_url", encoded)
        self.assertNotIn("vulnerabilities", encoded)

    def test_approved_caddy_otel_license_is_visible_without_changing_verdict(self):
        row = self.rows()[3]
        rendered = json.loads(self.render([row]))["rows"][0]
        self.assertEqual(rendered["license"], row["license"])
        self.assertNotIn("license_sha256", rendered)
        self.assertEqual(verify_dependency_changes([row], set()), 1)

    def test_unknown_license_digest_is_exact_bounded_and_not_an_exception(self):
        row = self.rows()[1]
        row["license"] = "withheld-license-canary"
        snapshot = json.dumps(row, sort_keys=True)
        encoded = self.render([row])
        rendered = json.loads(encoded)["rows"][0]
        self.assertEqual(rendered["license"], "<redacted>")
        self.assertEqual(
            rendered["license_sha256"],
            hashlib.sha256(row["license"].encode("ascii")).hexdigest(),
        )
        self.assertNotIn(row["license"], encoded)
        self.assertEqual(json.dumps(row, sort_keys=True), snapshot)
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([row], set())
        changed = {**row, "license": row["license"] + " "}
        changed_digest = json.loads(self.render([changed]))["rows"][0]["license_sha256"]
        self.assertNotEqual(changed_digest, rendered["license_sha256"])

    def test_license_digest_requires_exact_reviewed_non_license_identity(self):
        for field in ("change_type", "manifest", "ecosystem", "version", "package_url"):
            with self.subTest(field=field):
                row = {**self.rows()[1], "license": "withheld-license-canary"}
                row[field] = "withheld-identity-canary"
                rendered = json.loads(self.render([row]))["rows"][0]
                self.assertNotIn("license_sha256", rendered)

    def test_license_digest_does_not_expand_to_other_reviewed_manifests(self):
        row = self.rows()[2]
        row["manifest"] = "services/gateway/go.mod"
        row["license"] = "withheld-license-canary"
        rendered = json.loads(self.render([row]))["rows"][0]
        self.assertEqual(rendered["manifest"], "<redacted>")
        self.assertNotIn("license_sha256", rendered)

    def test_license_digest_inclusive_boundaries_and_output_cap(self):
        for size in (1, 160):
            with self.subTest(size=size):
                row = {**self.rows()[1], "license": "x" * size}
                encoded = self.render([row])
                rendered = json.loads(encoded)["rows"][0]
                self.assertEqual(
                    rendered["license_sha256"],
                    hashlib.sha256(row["license"].encode("ascii")).hexdigest(),
                )
        rows = [
            {**row, "license": "withheld-license-canary"} for row in self.rows()[1:]
        ] * 5
        encoded = self.render(rows)
        self.assertEqual(encoded, self.render(list(reversed(rows))))
        self.assertLessEqual(len(encoded), 4096)
        self.assertTrue(encoded.isascii())
        self.assertTrue(json.loads(encoded)["truncated"])
        self.assertNotIn("withheld-", encoded)

    def test_license_digest_rejects_unbounded_or_unsafe_values(self):
        for value in (
            None,
            "",
            "x" * 161,
            "bad\nvalue",
            "bad\x00value",
            "é",
            [],
            {},
            True,
        ):
            with self.subTest(value=value):
                row = {**self.rows()[1], "license": value}
                rendered = json.loads(self.render([row]))["rows"][0]
                self.assertNotIn("license_sha256", rendered)
        row = self.rows()[1]
        del row["license"]
        self.assertNotIn("license_sha256", json.loads(self.render([row]))["rows"][0])

    def test_null_license_is_not_conflated_with_missing_or_unreviewed_license(self):
        for value, present, expected in (
            (None, True, None),
            (None, False, "<redacted>"),
            ("withheld-license-canary", True, "<redacted>"),
            (False, True, "<redacted>"),
            (["AGPL-3.0"], True, "<redacted>"),
        ):
            with self.subTest(value=value, present=present):
                row = self.rows()[0]
                if present:
                    row["license"] = value
                else:
                    del row["license"]
                payload = json.loads(self.render([row]))
                self.assertEqual(payload["rows"][0]["license"], expected)

    def test_control_bearing_oversized_and_unreviewed_fields_are_redacted(self):
        for field in (
            "change_type",
            "manifest",
            "ecosystem",
            "version",
            "package_url",
            "license",
        ):
            for value in (
                "withheld-value-canary",
                "\n::error::withheld-control-canary",
                "\x00withheld-control-canary",
                "\u202ewithheld-control-canary",
                "x" * 161,
                [],
                {},
                True,
            ):
                with self.subTest(field=field, value=value):
                    row = self.rows()[1]
                    row[field] = value
                    encoded = self.render([row])
                    self.assertEqual(
                        json.loads(encoded)["rows"][0][field], "<redacted>"
                    )
                    self.assertNotIn("withheld-", encoded)
                    self.assertNotIn("\n", encoded)
                    self.assertNotIn("\x00", encoded)
        row = self.rows()[1]
        row["name"] = "howett.net/plist\n::error::withheld-name-canary"
        self.assertEqual(json.loads(self.render([row]))["rows"], [])

    def test_malformed_rows_and_non_list_payloads_do_not_escape_into_output(self):
        for payload in (
            None,
            "withheld-payload-canary",
            {},
            [None, [], {}, {"name": []}],
        ):
            with self.subTest(payload=payload):
                encoded = self.render(payload)
                self.assertEqual(json.loads(encoded)["rows"], [])
                self.assertNotIn("withheld-", encoded)

    def test_output_is_deterministic_bounded_and_reports_truncation(self):
        rows = self.rows() * 5
        encoded = self.render(rows)
        self.assertEqual(encoded, self.render(list(reversed(rows))))
        payload = json.loads(encoded)
        self.assertEqual(len(payload["rows"]), 8)
        self.assertEqual(len({row["name"] for row in payload["rows"]}), 4)
        self.assertTrue(payload["truncated"])
        self.assertLessEqual(len(encoded), 4096)
        self.assertTrue(encoded.isascii())
        self.assertNotIn("\n", encoded)
        self.assertEqual(
            encoded,
            json.dumps(
                payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ),
        )
        self.assertFalse(json.loads(self.render(self.rows() * 2))["truncated"])

    def test_four_exact_targets_survive_six_existing_service_copies(self):
        rows = self.rows()
        for original in self.rows()[2:]:
            for manifest in (
                "services/gateway/go.mod",
                "services/ws-hub/go.mod",
                "services/file-processor/go.mod",
            ):
                rows.append({**original, "manifest": manifest})
        payload = json.loads(self.render(rows))
        exact = [row for row in payload["rows"] if row["manifest"] != "<redacted>"]
        self.assertEqual(len(exact), 4)
        self.assertEqual(len({row["name"] for row in exact}), 4)
        self.assertTrue(payload["truncated"])
        self.assertEqual(self.render(rows), self.render(list(reversed(rows))))

    def test_trufflehog_marker_reports_only_strict_raw_self_consistency(self):
        for version, purl, expected in (
            (
                "b" * 40,
                "pkg:github/trufflesecurity/trufflehog@" + "b" * 40,
                "<matches-40-hex-version>",
            ),
            (
                "B" * 40,
                "pkg:github/trufflesecurity/trufflehog@" + "B" * 40,
                "<redacted>",
            ),
            (
                "g" * 40,
                "pkg:github/trufflesecurity/trufflehog@" + "g" * 40,
                "<redacted>",
            ),
            (
                "b" * 39,
                "pkg:github/trufflesecurity/trufflehog@" + "b" * 39,
                "<redacted>",
            ),
            (
                "b" * 41,
                "pkg:github/trufflesecurity/trufflehog@" + "b" * 41,
                "<redacted>",
            ),
            (
                "b" * 40 + "\n",
                "pkg:github/trufflesecurity/trufflehog@" + "b" * 40 + "\n",
                "<redacted>",
            ),
            (
                "b" * 40,
                "pkg:github/trufflesecurity/trufflehog@" + "a" * 40,
                "<redacted>",
            ),
            ("b" * 40, "pkg:github/other/package@" + "b" * 40, "<redacted>"),
            ([], "withheld-purl-canary", "<redacted>"),
            (None, "withheld-purl-canary", "<redacted>"),
        ):
            with self.subTest(version=version, purl=purl):
                row = self.rows()[0]
                row["version"] = version
                row["package_url"] = purl
                encoded = self.render([row])
                identity = json.loads(encoded)["rows"][0]
                self.assertEqual(identity["version"], "<redacted>")
                self.assertEqual(identity["package_url"], expected)
                self.assertNotIn("b" * 40, encoded)
                self.assertNotIn("withheld-", encoded)
        row = self.rows()[0]
        row["name"] = "other/package"
        self.assertEqual(json.loads(self.render([row]))["rows"], [])
        rows = [self.rows()[0]]
        for version in ("", "x" * 40, None, []):
            rows.append(
                {
                    **self.rows()[0],
                    "version": version,
                    "package_url": "withheld-purl-canary",
                }
            )
        payload = json.loads(self.render(rows))
        self.assertEqual(len(payload["rows"]), 2)
        self.assertTrue(payload["truncated"])
        self.assertEqual(
            sum(
                row["package_url"] == "<matches-40-hex-version>"
                for row in payload["rows"]
            ),
            1,
        )

    def test_oversized_top_level_encoding_uses_bounded_empty_fallback(self):
        module = "scripts.quality.verify_dependency_review_scope"
        real_dumps = json.dumps
        oversized_once = False

        def oversized_first_payload(value, **kwargs):
            nonlocal oversized_once
            if (
                isinstance(value, dict)
                and value.get("diagnostic") == "dependency-review-identities-v1"
                and not oversized_once
            ):
                oversized_once = True
                return "withheld-encoding-canary" + "x" * 4096
            return real_dumps(value, **kwargs)

        with patch(f"{module}.json.dumps", side_effect=oversized_first_payload):
            encoded = self.render(self.rows())
        payload = json.loads(encoded)
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["truncated"])
        self.assertLessEqual(len(encoded), 4096)
        self.assertNotIn("withheld-", encoded)

    def test_diagnostics_do_not_mutate_rows_or_make_caddy_identity_acceptable(self):
        rows = self.rows()
        snapshot = json.dumps(rows, sort_keys=True)
        self.render(rows)
        self.assertEqual(json.dumps(rows, sort_keys=True), snapshot)
        # The exact caddy row is accepted; diagnostics must not widen a mutated one.
        mutated = {**rows[2], "license": "MIT"}
        with self.assertRaisesRegex(ValueError, "unexpected package"):
            verify_dependency_changes([mutated], set())

    def test_changes_phase_prints_diagnostics_before_original_identity_failure(self):
        module = "scripts.quality.verify_dependency_review_scope"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changes.json"
            # The unreviewed LicenseRef row is checked by the guard but is not a
            # diagnostic target, so it fails the run without adding diagnostic rows.
            unreviewed = action_row(
                (
                    "added",
                    "services/gateway/go.mod",
                    "gomod",
                    "example.test/unreviewed",
                    "1.0.0",
                    "pkg:golang/example.test/unreviewed@1.0.0",
                    LICENSE_REF,
                )
            )
            path.write_text(json.dumps([*self.rows(), unreviewed]), encoding="utf-8")
            argv = [
                "verify",
                "changes",
                "--base-sha",
                "0" * 40,
                "--changes-file",
                str(path),
            ]
            with (
                patch(f"{module}.preflight", return_value=set()),
                patch.object(sys, "argv", argv),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                with self.assertRaisesRegex(ValueError, "unexpected package"):
                    main()
            self.assertTrue(output.getvalue(), "bounded identity diagnostics missing")
            payload = json.loads(output.getvalue())
            self.assertEqual(len(payload["rows"]), 4)
            self.assertNotIn("verified comparison", output.getvalue())

    def test_malformed_comparison_still_fails_before_any_diagnostic(self):
        module = "scripts.quality.verify_dependency_review_scope"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changes.json"
            row = self.rows()[1]
            row["license"] = []
            path.write_text(json.dumps([row]), encoding="utf-8")
            argv = [
                "verify",
                "changes",
                "--base-sha",
                "0" * 40,
                "--changes-file",
                str(path),
            ]
            with (
                patch(f"{module}.preflight", return_value=set()),
                patch.object(sys, "argv", argv),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                with self.assertRaisesRegex(ValueError, "invalid license field"):
                    main()
            self.assertEqual(output.getvalue(), "")


class ExtendedCaddyJoseExceptionTests(unittest.TestCase):
    def test_exact_three_advisories_have_identical_scope_and_expiry(self):
        self.assertEqual(
            {record["ghsa"] for record in GHSA_EXCEPTIONS},
            {CADDY_JOSE_GHSA, "GHSA-4w3g-jfj2-cw2q", "GHSA-vvm8-gf78-28g4"},
        )
        first = GHSA_EXCEPTIONS[0]
        for record in GHSA_EXCEPTIONS:
            for field in (
                "owner",
                "expires",
                "manifest",
                "ecosystem",
                "name",
                "version",
            ):
                self.assertEqual(record[field], first[field])

    def test_each_advisory_accepts_only_the_exact_live_scope(self):
        for record in GHSA_EXCEPTIONS:
            with self.subTest(advisory=record["ghsa"]):
                row = _advisory_row(
                    record["manifest"],
                    record["name"],
                    record["version"],
                    record["ghsa"],
                )
                self.assertEqual(
                    verify_ghsa_exception_rows([row], today=date(2027, 1, 9)), 1
                )
                for day in (date(2027, 1, 10), date(2027, 1, 11)):
                    with self.assertRaises(ValueError):
                        verify_ghsa_exception_rows([row], today=day)
                for manifest, name, version in (
                    ("services/gateway/go.mod", record["name"], record["version"]),
                    (
                        record["manifest"],
                        "github.com/go-jose/go-jose/v4",
                        record["version"],
                    ),
                    (record["manifest"], record["name"], "3.0.4"),
                ):
                    wrong = _advisory_row(manifest, name, version, record["ghsa"])
                    with self.assertRaises(ValueError):
                        verify_ghsa_exception_rows([wrong], today=date(2027, 1, 9))


if __name__ == "__main__":
    unittest.main()
