"""Source-only guards for AUD-423 factual documentation alignment.

These checks read the private source snapshot and its documentation overlay.
They do not import application packages or start services.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNSUPPORTED_PERFORMANCE_CLAIMS = (
    "(10,000 items)",
    "~45.2 ms",
    "<0.98 ms",
    "~46x Faster",
    "~2,500 req/sec",
    "10,000+ req/sec",
    "<5ms latency",
    "4x Concurrency",
    "0 Stampedes",
    "~1.4 MB",
    "<485 KB",
    "65% Smaller",
    "High-Concurrency Real-Time Hub",
    "high-throughput WebSockets",
    "extreme scalability",
    "thousands of concurrent WebSocket connections",
    "microsecond performance is critical",
    "lightweight bundles (<500 KB JS budget)",
    "(10 000 элементов)",
    "~45.2 мс",
    "<0.98 мс",
    "~46x Быстрее",
    "~2 500 зап/сек",
    "10 000+ зап/сек",
    "<5мс задержка",
    "4x Пропускная способность",
    "0 Лавин кэша",
    "~1.4 МБ",
    "<485 КБ",
    "65% Легче",
    "Высокая пропускная способность WS",
    "тысячи параллельных WebSocket-соединений",
    "важна каждая микросекунда",
    "бандлы менее 500 КБ",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def has_current_cache_metric_names(document: str, auth_source: str) -> bool:
    expected = (
        "gateway_l1_cache_hits_total",
        "gateway_l1_cache_misses_total",
    )
    return all(
        name in document and f'Name: "{name}"' in auth_source for name in expected
    )


def has_unsupported_performance_claim(document: str) -> bool:
    return any(claim in document for claim in UNSUPPORTED_PERFORMANCE_CLAIMS)


def has_local_https_scope(deploy_document: str, caddy: str, compose: str) -> bool:
    return (
        "Production browser traffic" in deploy_document
        and "must use HTTPS" in deploy_document
        and "same-origin" in deploy_document
        and "http://localhost" in deploy_document
        and "Caddy on port 80" in deploy_document
        and ":80 {" in caddy
        and "handle /static/*" in caddy
        and "handle /storage/*" in caddy
        and "auto_https disable_redirects" in caddy
        and '- "80:80"' in compose
        and '- "443:443"' in compose
        and "local full-Compose Caddyfile serves the app" in deploy_document
        and "without an HTTPS redirect" in deploy_document
    )


def has_local_access_point_bindings(document: str, compose: str) -> bool:
    mappings = (
        ("http://localhost", '"80:80"'),
        ("http://localhost:8000/api/docs", "127.0.0.1:8000:8000"),
        ("http://localhost:8080", "127.0.0.1:8080:8080"),
        ("ws://localhost:8083/ws", "127.0.0.1:8083:8081"),
        ("localhost:3000", "127.0.0.1:3000:3000"),
        ("localhost:9090", "127.0.0.1:9090:9090"),
        ("localhost:4040", "127.0.0.1:4040:4040"),
    )
    return all(url in document and binding in compose for url, binding in mappings)


def has_current_pyroscope_version(document: str, compose: str) -> bool:
    image = re.search(r"grafana/pyroscope:([^@\s]+)@sha256:", compose)
    return (
        image is not None
        and image.group(1) == "2.3.1"
        and "Pyroscope 2.3.1" in document
        and "grafana/pyroscope:2.3.1" in document
        and "Pyroscope 1.19" not in document
        and "grafana/pyroscope:1.19.1" not in document
    )


FRONT_DOOR_DOC_CLAIM = (
    "On non-exempt requests, the Gateway applies a client-IP front-door bucket"
)
AUTHENTICATED_USER_DOC_CLAIM = (
    "after JWT validation, authenticated requests also consume a separate "
    "verified user-ID bucket"
)


def has_scoped_password_claim(document: str, auth_source: str) -> bool:
    verify_body = auth_source.split("def verify_password_sync(", maxsplit=1)[1].split(
        "\n\nasync def verify_password(", maxsplit=1
    )[0]
    verify_and_update_body = auth_source.split(
        "def verify_and_update_password_sync(", maxsplit=1
    )[1].split("\n\nasync def verify_and_update_password(", maxsplit=1)[0]
    return (
        "current password verifier accepts Argon2id hashes only" in document
        and "does not assert that every deployed account record has been inventoried or migrated"
        in document
        and "type=Type.ID" in auth_source
        and "only argon2id hashes are accepted" in auth_source
        and 'hashed_password.startswith("$argon2id$")' in verify_body
        and 'hashed_password.startswith("$argon2id$")' in verify_and_update_body
        and 'hashed_password.startswith("$argon2")' not in verify_body
        and 'hashed_password.startswith("$argon2")' not in verify_and_update_body
        and "bcrypt.checkpw" not in auth_source
        and "bcrypt.hashpw" not in auth_source
    )


def has_argon2_parameters_and_controls(document: str, auth_source: str) -> bool:
    return (
        "time cost 3, memory 32 MiB, parallelism 4" in document
        and re.search(r"ARGON2_TIME_COST\s*=\s*3", auth_source) is not None
        and re.search(r"ARGON2_MEMORY_COST_KIB\s*=\s*32768", auth_source) is not None
        and re.search(r"ARGON2_PARALLELISM\s*=\s*4", auth_source) is not None
        and "type=Type.ID" in auth_source
        and "max(1, _AUTH_EXECUTOR_WORKERS - 1)" in auth_source
        and "cgroup-aware CPU count" in auth_source
    )


def has_correct_fallback_claim(document: str, limiter_source: str) -> bool:
    fallback_body = limiter_source.split(
        "func (rl *RateLimiter) applyInMemoryFallback", maxsplit=1
    )[1].split("\n}", maxsplit=1)[0]
    front_door_body = limiter_source.split(
        "func (rl *RateLimiter) Middleware", maxsplit=1
    )[1].split("func (rl *RateLimiter) AuthenticatedMiddleware", maxsplit=1)[0]
    authenticated_body = limiter_source.split(
        "func (rl *RateLimiter) AuthenticatedMiddleware", maxsplit=1
    )[1].split("func (rl *RateLimiter) allow", maxsplit=1)[0]
    return (
        re.search(r"defaultFallbackLimit\s*=\s*3", limiter_source) is not None
        and re.search(r"defaultFallbackWindow\s*=\s*int64\(60\)", limiter_source)
        is not None
        and "3 requests per client key per 60-second window per process instance"
        in document
        and "HTTP 429" in document
        and FRONT_DOOR_DOC_CLAIM in document
        and AUTHENTICATED_USER_DOC_CLAIM in document
        and "isHealthPath(c.Request.URL.Path)" in front_door_body
        and "isPublicStaticRead(c.Request)" in front_door_body
        and "rl.allow(c, ctx, rl.getClientIPKey(c))" in front_door_body
        and "after Validate or Optional" in limiter_source
        and "claims.UserID != userID" in authenticated_body
        and 'rl.allow(c, ctx, "user:"+userID)' in authenticated_body
        and "http.StatusTooManyRequests" in fallback_body
        and "double Redis+memory failure" not in document
    )


def budget_values(document: str, row_label: str) -> set[int]:
    row = next(line for line in document.splitlines() if row_label in line)
    matches = re.findall(r"(?<!\d)(?:\d{1,3}(?:[, ]\d{3})+|\d+)(?!\d)", row)
    return {int(value.replace(",", "").replace(" ", "")) for value in matches}


class DocsSourceAlignmentTests(unittest.TestCase):
    def test_readme_profiles_and_budgets_are_source_bound(self) -> None:
        readme = read("README.md")
        readme_ru = read("README.ru.md")
        rust_bench = read("native/rust_ext/benches/conflict_bench.rs")
        rust_source = read("native/rust_ext/src/lib.rs")
        websocket_profile = read("tests/performance/ws_hub_10k_test.js")
        bundle_source = read("frontend/scripts/check-bundle-budget.mjs")

        self.assertRegex(rust_bench, r"for size in \[10, 50, 100, 500\]")
        self.assertRegex(rust_bench, r"n\s*<=\s*576")
        self.assertRegex(rust_source, r"MAX_CONFLICT_ITEMS:\s*usize\s*=\s*2500")
        self.assertIn("{ duration: '90s', target: 10000 }", websocket_profile)
        self.assertIn("errors: ['rate<0.01']", websocket_profile)
        self.assertIn("p(95)<2000", websocket_profile)
        self.assertIn("count>50000", websocket_profile)
        self.assertIn("count>=100", websocket_profile)
        self.assertIn("most VUs will get a 429", websocket_profile)

        source_budgets = {
            name: int(re.search(rf"{name}:\s*(\d+)", bundle_source).group(1))
            for name in (
                "mainJsRawKb",
                "initialJsGzipKb",
                "initialCssGzipKb",
                "generalLazyJsGzipKb",
                "passwordDictionaryRawKb",
                "passwordDictionaryGzipKb",
            )
        }
        self.assertEqual(
            source_budgets,
            {
                "mainJsRawKb": 500,
                "initialJsGzipKb": 420,
                "initialCssGzipKb": 40,
                "generalLazyJsGzipKb": 280,
                "passwordDictionaryRawKb": 1250,
                "passwordDictionaryGzipKb": 600,
            },
        )
        self.assertRegex(bundle_source, r"MAPLIBRE_LAZY_GZIP_KB\s*=\s*286")
        self.assertIn("bytes / 1024", bundle_source)
        expected_budget_values = {*source_budgets.values(), 286}

        for document, row_label, measurement_note in (
            (readme, "**Frontend transfer budgets**", "not measured bundle sizes"),
            (readme_ru, "**Лимиты передачи frontend**", "не измеренные размеры bundle"),
        ):
            with self.subTest(language=row_label):
                self.assertEqual(
                    budget_values(document, row_label), expected_budget_values
                )
                self.assertIn(measurement_note, document.lower())
        self.assertNotIn("<500 KB JS budget", readme)
        self.assertNotIn("менее 500 КБ", readme_ru)

        self.assertFalse(has_unsupported_performance_claim(readme + readme_ru))

        # Negative control: the detector must reject a stale headline timing.
        stale_readme = (
            readme + "\n| Schedule conflict solver (10,000 items) | ~45.2 ms |\n"
        )
        self.assertTrue(has_unsupported_performance_claim(stale_readme))

    def test_xfetch_semantics_and_prometheus_names_match_gateway_source(self) -> None:
        auth_source = read("services/gateway/middleware/auth.go")
        readme = read("README.md")
        readme_ru = read("README.ru.md")

        self.assertIn("Cache only positive revocation tombstones.", auth_source)
        self.assertIn(
            "shouldRefreshProbabilistic(entry.storedAt, m.l1TTL, 1.0)", auth_source
        )
        self.assertIn("m.redis.Exists(reqCtx, key)", auth_source)
        self.assertTrue(has_current_cache_metric_names(readme, auth_source))
        self.assertTrue(has_current_cache_metric_names(readme_ru, auth_source))
        self.assertIn("does not guarantee zero cache stampedes", readme)
        self.assertIn("не гарантирует отсутствие cache stampede", readme_ru)

        wrong_metric_mutant = readme.replace(
            "gateway_l1_cache_hits_total", "cache_l1_hits_total"
        )
        self.assertFalse(
            has_current_cache_metric_names(wrong_metric_mutant, auth_source)
        )

    def test_security_fallback_is_bounded_local_429_and_password_claim_is_scoped(
        self,
    ) -> None:
        security_doc = read("SECURITY.md")
        limiter_source = read("services/gateway/middleware/ratelimit.go")
        auth_source = read("app/auth/security.py")

        self.assertTrue(has_correct_fallback_claim(security_doc, limiter_source))
        self.assertIn("rl.getClientIPKey(c)", limiter_source)
        self.assertIn('rl.allow(c, ctx, "user:"+userID)', limiter_source)
        self.assertIn("if rl.limiter == nil", limiter_source)
        self.assertIn("if err != nil", limiter_source)
        revocation_source = read("services/gateway/middleware/auth.go")
        self.assertIn(
            "return false, failSecure, errRevocationStoreUnavailable", revocation_source
        )
        self.assertIn("if failSecure {", revocation_source)
        self.assertTrue(has_scoped_password_claim(security_doc, auth_source))
        self.assertTrue(has_argon2_parameters_and_controls(security_doc, auth_source))
        self.assertNotIn("All accounts use Argon2id", security_doc)
        for sla in (
            "| **Critical** | 24 hours | 48 hours | 7 days |",
            "| **High** | 48 hours | 5 days | 30 days |",
            "| **Medium** | 5 days | 14 days | 90 days |",
            "| **Low** | 5 days | 30 days | Best-effort |",
        ):
            self.assertIn(sla, security_doc)

        old_fallback_mutant = security_doc.replace(
            FRONT_DOOR_DOC_CLAIM,
            "use the client IP before authentication and switch to user ID afterward",
        )
        self.assertFalse(
            has_correct_fallback_claim(old_fallback_mutant, limiter_source)
        )
        old_fallback_mutant = security_doc.replace(
            "HTTP 429", "failing closed with 503 on double Redis+memory failure"
        )
        self.assertFalse(
            has_correct_fallback_claim(old_fallback_mutant, limiter_source)
        )
        weak_argon_mutant = security_doc.replace("parallelism 4", "parallelism 3")
        self.assertFalse(
            has_argon2_parameters_and_controls(weak_argon_mutant, auth_source)
        )
        unbounded_account_mutant = security_doc.replace(
            "does not assert that every deployed account record has been inventoried or migrated",
            "all accounts use Argon2id",
        )
        self.assertFalse(
            has_scoped_password_claim(unbounded_account_mutant, auth_source)
        )

    def test_local_http_and_production_https_scope_matches_edge_sources(self) -> None:
        deploy_en = read("docs/DEPLOY.en.md")
        deploy_ru = read("docs/DEPLOY.md")
        readme = read("README.md")
        readme_ru = read("README.ru.md")
        caddy = read("infrastructure/Caddyfile")
        compose = read("docker-compose.full.yml")

        self.assertTrue(has_local_https_scope(deploy_en, caddy, compose))
        self.assertIn("production браузерный трафик", deploy_ru)
        self.assertIn("через HTTPS", deploy_ru)
        self.assertIn("http://localhost", deploy_ru)
        self.assertIn("только для локальной разработки", deploy_ru)
        self.assertIn("describe the local full-Compose stack", readme)
        self.assertIn("локальному full-Compose стеку", readme_ru)
        self.assertTrue(has_local_access_point_bindings(readme, compose))
        self.assertTrue(has_local_access_point_bindings(readme_ru, compose))
        self.assertIn("./infrastructure/Caddyfile:/etc/caddy/Caddyfile:ro", compose)
        self.assertIn("reverse_proxy frontend:3000", caddy)
        self.assertTrue(has_current_pyroscope_version(readme, compose))
        self.assertTrue(has_current_pyroscope_version(readme_ru, compose))

        wrong_port_mutant = readme.replace("localhost:8080", "localhost:8082")
        self.assertFalse(has_local_access_point_bindings(wrong_port_mutant, compose))
        local_exception_mutant = deploy_en.replace("must use HTTPS", "may use HTTP")
        self.assertFalse(has_local_https_scope(local_exception_mutant, caddy, compose))
        old_pyroscope_mutant = readme.replace(
            "grafana/pyroscope:2.3.1", "grafana/pyroscope:1.19.1"
        )
        self.assertFalse(has_current_pyroscope_version(old_pyroscope_mutant, compose))

    def test_documented_image_tags_match_current_digest_pinned_dockerfiles(
        self,
    ) -> None:
        agents = read("AGENTS.md")
        deploy_en = read("docs/DEPLOY.en.md")
        deploy_ru = read("docs/DEPLOY.md")
        backend_dockerfile = read("backend.Dockerfile")
        frontend_dockerfile = read("frontend.Dockerfile")
        go_dockerfiles = (
            read("services/gateway/Dockerfile"),
            read("services/ws-hub/Dockerfile"),
            read("services/file-processor/Dockerfile"),
        )

        exact_tags = (
            re.search(r"FROM python:([^@\s]+)@sha256:", backend_dockerfile).group(1),
            re.search(r"FROM node:([^@\s]+)@sha256:", frontend_dockerfile).group(1),
            re.search(r"FROM golang:([^@\s]+)@sha256:", go_dockerfiles[0]).group(1),
            "gcr.io/distroless/static-debian12",
        )
        self.assertEqual(
            exact_tags[:3],
            (
                "3.14.8-slim-bookworm",
                "24.21.0-alpine",
                "1.26.10-alpine3.24",
            ),
        )
        for tag in exact_tags:
            with self.subTest(tag=tag):
                self.assertIn(tag, agents)
        self.assertIn("node:24.21.0-alpine", deploy_en)
        self.assertIn("node:24.21.0-alpine", deploy_ru)
        self.assertNotIn("digest-pinned `node:24-alpine`", deploy_en)
        self.assertNotIn("закреплённом по digest `node:24-alpine`", deploy_ru)
        self.assertTrue(
            all(
                "golang:1.26.10-alpine3.24@sha256:" in dockerfile
                for dockerfile in go_dockerfiles
            )
        )


if __name__ == "__main__":
    unittest.main()
