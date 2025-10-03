# Security Policy

## Supported Versions
We actively maintain and provide security updates for the latest released version of this project. Older versions may no longer receive security fixes, so upgrading to the most recent release is strongly recommended.

## Reporting a Vulnerability
If you discover a vulnerability, please report it privately so we can address it promptly. We aim to acknowledge new reports within 72 hours.

## Private Vulnerability Reporting
To report a vulnerability, use the **Security** tab on GitHub and open a new **Private vulnerability report**. Issues are disabled for vulnerability discussions; instead, please submit a GitHub Security Advisory so the team can work with you directly on mitigation and disclosure.

## Password Storage & Policy

- We hash passwords with Argon2id via Passlib using time cost **3**, memory cost **65536 KiB** (~64 MB) and parallelism **4**.
- Legacy bcrypt hashes are accepted for login and rehashed to Argon2id on success; bcrypt's 72-byte input limit is enforced during legacy hashing to prevent silent truncation issues.
- Password length requirements: **8–200 characters**. Unicode is fully supported and input is stored verbatim (no trimming or normalization).
- Password changes and account provisioning use the same policy and algorithm, and the behaviour is covered by automated tests.
