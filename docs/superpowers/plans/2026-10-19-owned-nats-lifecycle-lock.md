# Existing lifecycle-lock capability

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

The legacy in-place helper derives the sibling lock as state_root.parent / ('.' + state_root.name + '.lifecycle.lock'), creates it with O_CREAT|O_RDWR, and can wait indefinitely. It is not reused. Normal Core up already creates this sibling lock before signed state; the new capability will only read and lock that existing inode.

## Initial tests-first seam

acquire_existing_lifecycle_lock receives the explicit absolute state-root pin, the caller's Deadline and a sleep callback. The initial seam always returns None with no I/O. release_lifecycle_lock initially returns False with no descriptor operation. LifecycleLockLease is opaque and unavailable; it is not a signed-owner or runtime-admission result.

Three first tests require: a real exclusive lease blocks independent SH and EX nonblocking probes and leaves file content/metadata unchanged; the exact nofollow descriptor-relative root/ancestor walk and sibling-parent fd are used with read-only flags and each fd closes once; an already-expired acquisition attempts no instrumented OS/flock call. Initial expected outcome is two positive assertion failures and one expiry PASS. Actual hosted RED must precede implementation.

The later implementation contract checks the state-root directory itself as well as all ancestors, then opens only the existing sibling regular lock with O_NONBLOCK/O_NOFOLLOW/O_CLOEXEC. It uses the same deadline, no creation or writes, and a capped nonblocking contention wait. Release must attempt cleanup even after expiry, report failure on expiry/cleanup error, and never close a reused descriptor on a repeated call.

Unsupported-platform/capability cases, symlinks/FIFO, contention, replacement, post-acquisition expiry, idempotence, unlock/close faults and interrupt precedence remain explicit later tests before runtime wiring. A held advisory lock is cooperative serialization, not cryptographic ownership. Sequential path checks are not atomic, and network/FUSE syscalls cannot be hard-preempted. No Docker, SQL, HTTP, coordinator or CLI wiring, new credential, production target or outage enablement is included.

## Hosted initial result and test-platform contract

On 71b73b6, focused job 118349328377 reports 672 PASS / 3 FAIL in 189.03 seconds. Both positive lease tests fail because acquisition returns None; the expired no-I/O case passes. The third failure is the existing disabled-outage workflow hold. This is the required initial RED, not lock implementation acceptance.

The inventory gate rejects the new dynamic platform skip. Replace it with explicit required-capability assertions: this real-primitive cohort runs on the existing ubuntu-24.04 backend runner and must fail clearly if the runner loses its capabilities, rather than silently disappear. The repository still supports Windows developer workflows; this particular cohort requires POSIX. No skip identity, waiver, marker exclusion or inventory policy change is added. The fixture also guards flock throughout acquisition, release and probes, permitting only exact LOCK_UN, LOCK_SH|LOCK_NB and LOCK_EX|LOCK_NB operations before invoking the real syscall. Unsupported production capability tests remain independent later tests, not empty positive-path passes.

## Minimal lease implementation after observed RED

The first implementation opens only the existing sibling inode and retains all nofollow directory descriptors including the state root. It requests LOCK_EX|LOCK_NB, retries only EACCES/EAGAIN/EWOULDBLOCK contention, caps each injected sleep at 50 ms and the caller's remaining budget, and revalidates the directory chain and regular lock identity after acquisition. Clock and sleep injections must cooperate; neither a second clock nor a hard-preemption claim is introduced. Exceptional operations proceed only to cleanup.

Acquisition records successful flock before the post-call deadline check. Release consumes its cleanup state before clocks or descriptor operations, attempts unlock and reverse-order closes even when expired, and reports False on expiry/ordinary cleanup failure. Repeated release returns False without touching descriptors. Operation BaseException retains precedence over cleanup faults; cleanup interruptions propagate only after every retained descriptor receives one attempt. Ambiguous close outcomes are never retried.

The cohort now has twelve cases: the original three; live/expired release with exact unlock-before-reverse-close ordering and an actually recycled descriptor protected against repeated-release calls; four refusal paths (missing lock, root symlink, lock symlink, FIFO); and three unsupported API-capability cases with no I/O. Real-path tests check flags before syscalls and forbid reads/mutations so unsafe FIFO regressions cannot block. New source awaits hosted execution. Contention, replacement, acquisition-time expiry, additional capability/import cases, unlock/close faults and interrupt precedence still need dedicated evidence before any runtime wiring. Existing parser and reader behavior is unchanged.
