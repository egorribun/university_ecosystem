# ADR-001: Argon2id for Password Hashing

## Status
Accepted

## Context
We needed to choose a password hashing algorithm that balances security, performance, and future-proofing.

## Decision
We chose **Argon2id** as our password hashing algorithm.

## Rationale
1. **Winner of Password Hashing Competition (2015)** - Academic peer review
2. **Memory-hard** - Resistant to GPU/ASIC attacks
3. **Argon2id variant** - Combines Argon2i (side-channel resistance) and Argon2d (GPU resistance)
4. **Configurable** - Memory, iterations, parallelism tunable
5. **Modern** - Recommended by OWASP 2024

## Alternatives Considered
- **bcrypt**: Good, but lacks memory-hardness. Vulnerable to specialized hardware.
- **scrypt**: Memory-hard but complex to tune correctly.
- **PBKDF2**: Legacy, not memory-hard.

## Consequences
- Slightly higher memory usage during login (~64MB default)
- Requires `argon2-cffi` or `passlib` dependency
- Migration script needed if switching from bcrypt

## References
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [RFC 9106: Argon2](https://www.rfc-editor.org/rfc/rfc9106)
