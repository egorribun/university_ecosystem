"""Runtime guards for the approved dnspython security update."""

import dns.exception
import dns.message
import dns.name
import dns.resolver
import dns.rrset
import pytest
from email_validator import validate_email


def _compression_chain(hops: int) -> bytes:
    return b"\x00\x00" + b"".join(
        bytes((0xC0, offset)) for offset in range(0, hops * 2, 2)
    )


def test_dns_compression_accepts_sixteen_pointers() -> None:
    wire = _compression_chain(16)
    name, consumed = dns.name.from_wire(wire, len(wire) - 2)
    assert name == dns.name.root
    assert consumed == 2


def test_dns_compression_rejects_seventeenth_pointer() -> None:
    wire = _compression_chain(17)
    with pytest.raises(dns.exception.FormError) as error:
        dns.name.from_wire(wire, len(wire) - 2)
    assert type(error.value).__name__ == "PointerChainTooLong"


def test_email_validator_consumes_dnspython_mx_wire_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = dns.resolver.Resolver(configure=False)
    query = dns.message.make_query("university.edu", "MX")
    response = dns.message.make_response(query)
    response.answer.append(
        dns.rrset.from_text(
            "university.edu.",
            60,
            "IN",
            "MX",
            "20 backup.university.edu.",
            "10 mail.university.edu.",
        )
    )
    wire = response.to_wire()
    calls: list[tuple[str, str]] = []

    def resolve(
        actual_resolver: dns.resolver.Resolver,
        domain: str,
        record_type: str,
    ) -> dns.rrset.RRset:
        assert actual_resolver is resolver
        assert (domain, record_type) == ("university.edu", "MX")
        calls.append((domain, record_type))
        return dns.message.from_wire(wire).answer[0]

    monkeypatch.setattr(dns.resolver.Resolver, "resolve", resolve)
    result = validate_email(
        "student@UNIVERSITY.EDU",
        check_deliverability=True,
        test_environment=False,
        dns_resolver=resolver,
    )
    assert result.normalized == "student@university.edu"
    assert result.mx == [(10, "mail.university.edu"), (20, "backup.university.edu")]
    assert result.mx_fallback_type is None
    assert calls == [("university.edu", "MX")]
