"""Generated RPC consumers keep the reviewed Go network security floor."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GeneratedGoSecurityDependencyPinsTests(unittest.TestCase):
    def _assert_network_security_floor(self, go_mod: str) -> None:
        # GO-2026-6860 / CVE-2026-78661 is fixed in x/net v0.62.0.
        # Workspace MVS must not hide an outdated standalone generated module.
        match = re.search(
            r"^\s*golang\.org/x/net v(\d+)\.(\d+)\.(\d+) // indirect$", go_mod, re.M
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertGreaterEqual(tuple(map(int, match.groups())), (0, 62, 0))
        # This standalone generated module has no replacements. Reject the
        # directive itself so quoted or escaped module paths cannot bypass it.
        self.assertNotRegex(go_mod, r"(?m)^\s*replace\b")

    def test_standalone_module_requires_fixed_network_release(self) -> None:
        go_mod = (ROOT / "gen/go/go.mod").read_text(encoding="utf-8")
        self._assert_network_security_floor(go_mod)

    def test_replacement_syntax_cannot_bypass_network_security_floor(self) -> None:
        go_mod = (ROOT / "gen/go/go.mod").read_text(encoding="utf-8")
        self._assert_network_security_floor(go_mod)
        # Each directive is accepted by Go 1.26.10's go mod edit -json parser.
        for directive in (
            "replace golang.org/x/net => golang.org/x/net v0.60.0",
            'replace "golang.org/x/net" => golang.org/x/net v0.60.0',
            'replace "golang.org/x/\\x6eet" => golang.org/x/net v0.60.0',
            'replace "golang.org/x/net" "v0.62.0" => "golang.org/x/net" "v0.60.0"',
            "replace (\n golang.org/x/net => golang.org/x/net v0.60.0\n)",
            'replace (\n "golang.org/x/net" => golang.org/x/net v0.60.0\n)',
            'replace(\n "golang.org/x/net" => golang.org/x/net v0.60.0\n)',
            'replace (\n "golang.org/x/\\x6eet" => golang.org/x/net v0.60.0\n)',
        ):
            with self.subTest(directive=directive), self.assertRaises(AssertionError):
                self._assert_network_security_floor(f"{go_mod}\n{directive}\n")

    def test_comment_about_replacements_does_not_change_security_floor(self) -> None:
        go_mod = (ROOT / "gen/go/go.mod").read_text(encoding="utf-8")
        self._assert_network_security_floor(
            f'{go_mod}\n// replace "golang.org/x/net" => golang.org/x/net v0.60.0\n'
        )

    def test_selected_network_modules_have_both_checksum_records(self) -> None:
        go_mod = (ROOT / "gen/go/go.mod").read_text(encoding="utf-8")
        sums = (ROOT / "gen/go/go.sum").read_text(encoding="utf-8")
        for module in ("golang.org/x/net", "golang.org/x/text"):
            with self.subTest(module=module):
                match = re.search(
                    rf"^\s*{re.escape(module)} (v\S+) // indirect$", go_mod, re.M
                )
                self.assertIsNotNone(match)
                assert match is not None
                for suffix in ("", "/go.mod"):
                    self.assertRegex(
                        sums,
                        rf"(?m)^{re.escape(module)} {re.escape(match.group(1) + suffix)} h1:[A-Za-z0-9+/]{{43}}=$",
                    )


if __name__ == "__main__":
    unittest.main()
