"""Closure test for CSP default-src hardening."""

from app.core.policies.csp import ContentSecurityPolicy


def test_csp_adds_default_src_when_custom_policy_omits_it():
    policy = ContentSecurityPolicy(custom_policy="script-src 'self'").generate()

    assert policy.startswith("default-src 'self';")
    assert "script-src 'self'" in policy
