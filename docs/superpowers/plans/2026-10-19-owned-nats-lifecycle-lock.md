# Existing lifecycle-lock capability

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

The legacy in-place helper derives the sibling lock as state_root.parent / ('.' + state_root.name + '.lifecycle.lock'), creates it with O_CREAT|O_RDWR, and can wait indefinitely. It is not reused. Normal Core up already creates this sibling lock before signed state; the new capability will only read and lock that existing inode.

## Initial tests-first seam

acquire_existing_lifecycle_lock receives the explicit absolute state-root pin, the caller's Deadline and a sleep callback. The initial seam always returns None with no I/O. release_lifecycle_lock initially returns False with no descriptor operation. LifecycleLockLease is opaque and unavailable; it is not a signed-owner or runtime-admission result.

Three first tests require: a real exclusive lease blocks independent SH and EX nonblocking probes and leaves file content/metadata unchanged; the exact nofollow descriptor-relative root/ancestor walk and sibling-parent fd are used with read-only flags and each fd closes once; an already-expired acquisition attempts no instrumented OS/flock call. Initial expected outcome is two positive assertion failures and one expiry PASS. Actual hosted RED must precede implementation.

The later implementation contract checks the state-root directory itself as well as all ancestors, then opens only the existing sibling regular lock with O_NONBLOCK/O_NOFOLLOW/O_CLOEXEC. It uses the same deadline, no creation or writes, and a capped nonblocking contention wait. Release must attempt cleanup even after expiry, report failure on expiry/cleanup error, and never close a reused descriptor on a repeated call.

Unsupported-platform/capability cases, symlinks/FIFO, contention, replacement, post-acquisition expiry, idempotence, unlock/close faults and interrupt precedence remain explicit later tests before runtime wiring. A held advisory lock is cooperative serialization, not cryptographic ownership. Sequential path checks are not atomic, and network/FUSE syscalls cannot be hard-preempted. No Docker, SQL, HTTP, coordinator or CLI wiring, new credential, production target or outage enablement is included.
