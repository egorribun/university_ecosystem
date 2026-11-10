"""Shared OpenAPI client-error documentation."""

from __future__ import annotations

from app.api import openapi_responses as docs


def test_combine_keeps_every_status_and_both_descriptions_for_a_shared_code() -> None:
    merged = docs.combine(
        docs.UNAUTHENTICATED, docs.CSRF_REJECTED, docs.ADMIN_FORBIDDEN
    )

    assert set(merged) == {401, 403}
    assert merged[401] == docs.UNAUTHENTICATED[401]
    description = merged[403]["description"]
    assert docs.CSRF_REJECTED[403]["description"] in description
    assert docs.ADMIN_FORBIDDEN[403]["description"] in description


def test_combine_does_not_mutate_the_shared_entries() -> None:
    before = dict(docs.CSRF_REJECTED[403])

    docs.combine(docs.CSRF_REJECTED, docs.ADMIN_FORBIDDEN)

    assert docs.CSRF_REJECTED[403] == before


def test_csp_report_inline_rate_limit_doc_matches_the_shared_entry() -> None:
    # csp_report.py documents its responses inline to keep the import set the
    # sqlmap gate reviews; its 429 text must still match the shared entry.
    from app.api.internal.csp_report import router

    (route,) = router.routes
    assert route.responses[429] == docs.RATE_LIMITED[429]


def test_every_shared_entry_is_a_client_error() -> None:
    for entry in (
        docs.INVALID_HOST,
        docs.UNAUTHENTICATED,
        docs.CSRF_REJECTED,
        docs.ADMIN_FORBIDDEN,
        docs.RATE_LIMITED,
    ):
        assert all(400 <= int(code) < 500 for code in entry)
