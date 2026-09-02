from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from packaging.version import Version

from scripts.osv_batch_audit import (
    OsvBatchError,
    OsvBatchService,
    ResolvedDependency,
    SkippedDependency,
    _report,
)


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.max_redirects = 0

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, kwargs.get("json")))
        if not self.responses:
            raise AssertionError("unexpected OSV request")
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, None))
        if not self.responses:
            raise AssertionError("unexpected OSV request")
        return self.responses.pop(0)


def _detail(identifier: str = "PYSEC-2099-1") -> dict[str, Any]:
    return {
        "id": identifier,
        "schema_version": "1.0.0",
        "aliases": ["CVE-2099-0001"],
        "summary": "example vulnerability",
        "published": "2099-01-01T00:00:00Z",
        "affected": [
            {
                "package": {"name": "demo-package", "ecosystem": "PyPI"},
                "ranges": [
                    {
                        "type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "2.0.0"}],
                    }
                ],
            }
        ],
    }


def _service(
    responses: list[_Response], sleeps: list[float] | None = None
) -> OsvBatchService:
    return OsvBatchService(
        session=_Session(responses),
        attempts=3,
        batch_size=2,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_batch_service_parses_details_and_preserves_skipped_records() -> None:
    service = _service(
        [
            _Response(200, {"results": [{"vulns": [{"id": "PYSEC-2099-1"}]}]}),
            _Response(200, _detail()),
        ]
    )
    resolved = ResolvedDependency("demo-package", Version("1.0.0"))
    skipped = SkippedDependency("url-package", "URL requirement")

    result = list(service.query_all(iter([resolved, skipped])))

    assert result[0][0] == resolved
    assert [str(v.id) for v in result[0][1]] == ["PYSEC-2099-1"]
    assert result[0][1][0].aliases == {"CVE-2099-0001"}
    assert result[0][1][0].fix_versions == [Version("2.0.0")]
    assert result[1] == (skipped, [])


def test_batch_service_retries_transient_response_and_sorts_report() -> None:
    sleeps: list[float] = []
    service = _service(
        [
            _Response(500, {}),
            _Response(200, {"results": [{}]}),
        ],
        sleeps,
    )
    resolved = ResolvedDependency("demo-package", Version("1.0.0"))

    result = list(service.query_all(iter([resolved])))

    assert result == [(resolved, [])]
    assert sleeps == [1.0]


def test_shared_vulnerability_detail_is_parsed_for_each_package() -> None:
    """One OSV record can affect multiple packages with different fixes."""

    payload = _detail()
    payload["affected"].append(
        {
            "package": {"name": "other-package", "ecosystem": "PyPI"},
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "3.0.0"}],
                }
            ],
        }
    )
    service = _service(
        [
            _Response(
                200,
                {
                    "results": [
                        {"vulns": [{"id": "PYSEC-2099-1"}]},
                        {"vulns": [{"id": "PYSEC-2099-1"}]},
                    ]
                },
            ),
            _Response(200, payload),
        ]
    )
    first = ResolvedDependency("demo-package", Version("1.0.0"))
    second = ResolvedDependency("other-package", Version("1.0.0"))

    result = list(service.query_all(iter([first, second])))

    assert result[0][1][0].fix_versions == [Version("2.0.0")]
    assert result[1][1][0].fix_versions == [Version("3.0.0")]
    assert [url for url, _ in service._session.calls].count(
        "https://api.osv.dev/v1/vulns/PYSEC-2099-1"
    ) == 1


@pytest.mark.parametrize(
    "responses",
    [
        [_Response(200, {"results": []})],
        [
            _Response(200, {"results": [{"vulns": [{"id": "UNKNOWN"}]}]}),
            _Response(200, {}),
        ],
        [
            _Response(200, {"results": [{"vulns": [{"id": "PYSEC-1"}]}]}),
            _Response(200, {"id": "PYSEC-1", "affected": []}),
        ],
        [
            _Response(200, {"results": [{"vulns": [{"id": "PYSEC-1"}]}]}),
            _Response(
                200,
                {
                    "id": "PYSEC-1",
                    "withdrawn": False,
                    "affected": [],
                },
            ),
        ],
        [_Response(302, {})],
    ],
)
def test_batch_service_rejects_incomplete_or_malformed_osv_payloads(
    responses: list[_Response],
) -> None:
    service = _service(responses)
    resolved = ResolvedDependency("demo-package", Version("1.0.0"))

    with pytest.raises(OsvBatchError):
        list(service.query_all(iter([resolved])))


def test_batch_service_rejects_duplicate_dependency_keys() -> None:
    service = _service([])
    resolved = ResolvedDependency("demo-package", Version("1.0.0"))

    with pytest.raises(OsvBatchError, match="duplicate"):
        list(service.query_all(iter([resolved, resolved])))


def test_single_package_query_is_rejected() -> None:
    service = _service([])
    with pytest.raises(OsvBatchError, match="query_all"):
        service.query(ResolvedDependency("demo-package", Version("1.0.0")))


def test_report_is_deterministic_and_marks_findings() -> None:
    dependency = ResolvedDependency("Demo_Package", Version("1.0.0"))
    skipped = SkippedDependency("url-package", "URL requirement")
    payload, has_findings = _report(
        [
            (dependency, []),
            (skipped, []),
        ]
    )

    assert not has_findings
    assert payload == {
        "dependencies": [
            {"name": "demo-package", "version": "1.0.0", "vulns": []},
            {"name": "url-package", "skip_reason": "URL requirement"},
        ],
        "fixes": [],
    }
    assert json.dumps(payload, sort_keys=True)


def test_report_marks_advisory_presence() -> None:
    vulnerability = OsvBatchService._parse_vulnerability(
        "PYSEC-2099-1", _detail(), "demo-package"
    )
    assert vulnerability is not None
    payload, has_findings = _report(
        [(ResolvedDependency("demo-package", Version("1.0.0")), [vulnerability])]
    )
    assert has_findings
    assert payload["dependencies"][0]["vulns"][0]["aliases"] == ["CVE-2099-0001"]


def test_report_path_is_not_created_by_helper(tmp_path: Path) -> None:
    # Keep this test as a guard that report generation stays a pure transformation;
    # atomic filesystem writes belong exclusively to the CLI boundary.
    payload, _ = _report([])
    assert not list(tmp_path.iterdir())
    assert payload == {"dependencies": [], "fixes": []}
