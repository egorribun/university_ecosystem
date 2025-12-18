# ADR 003: Session Fingerprinting for Security

**Status**: Accepted  
**Date**: 2024-12-18

## Context

Session hijacking attacks involve stealing session tokens (via XSS, network interception, etc.) and using them from a different device/location. Traditional session management only validates the token itself, not the context in which it's used.

Indicators of potential session hijacking:
- User-Agent change mid-session
- Impossible travel (IP change faster than physically possible)
- Sudden language preference change

## Decision

Implement session fingerprinting to detect suspicious session usage.

### Fingerprint Components

| Component | Weight | Volatility |
|-----------|--------|------------|
| User-Agent | High | Low (rarely changes) |
| Accept-Language | Medium | Very Low |
| IP Address | Low | High (mobile, VPN) |

### Fingerprint Hash

Hash is computed from stable components only (User-Agent + Accept-Language):

```python
def _compute_fingerprint_hash(user_agent: str, accept_language: str, ip_address: str) -> str:
    content = f"{user_agent}|{accept_language}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]
```

IP is stored for logging but not included in hash due to volatility.

### Severity Levels

| Mismatch Type | Severity | Action |
|---------------|----------|--------|
| User-Agent changed | High | Log warning, consider termination |
| Multiple fields changed | Medium | Log info, monitor |
| IP only changed | Low | Log debug, allow |

### Suspicious Activity Detection

```python
class SuspiciousActivityDetector:
    def check_fingerprint_mismatch(...)  # Compare fingerprints
    def check_rapid_location_change(...) # Impossible travel detection
```

## Consequences

### Positive
- Detection of session hijacking attempts
- Structured security logging
- Foundation for automated session termination

### Negative
- False positives possible (browser updates, VPN changes)
- Additional logging volume
- Requires careful tuning of thresholds

### Future Work
- Automatic session termination on high-severity events
- User notification of suspicious activity
- Geographic impossibility detection using IP geolocation
