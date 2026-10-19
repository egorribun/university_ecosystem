# Existing signed-owner file boundary

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

The pure supplied-byte parser has 66 verified cases. The first reader slice introduced an unavailable seam and 24 existing-file tests. After observed RED it was implemented; all 24 passed on e5588a0, job 118329557122, along with all 66 parser cases. This remains a read-only metadata boundary, not runtime admission.

## Required contract

- Use the caller's same Deadline; stop dispatching new reads/stats/opens after observed expiry.
- Initially walk from / through each absolute state-root component and .secrets using directory-relative O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC. Reject traversal components and initial symlink ancestors.
- Open only live-stand.json and live-stand-owner.key relative to the retained secrets descriptor, read-only with O_NOFOLLOW/O_NONBLOCK/O_CLOEXEC; require regular files.
- Marker cap is 65536 bytes, key exactly 32 bytes. Reads must remain bounded, including wrong/oversized inputs; no creation, replacement, chmod or rotation of existing files.
- Close every acquired descriptor even after expiry. Local, network and FUSE syscalls cannot be hard-preempted by these pre/post checks.
- Return repr-private SIGNED_METADATA only after the existing parser succeeds. Initial descriptor traversal does not establish that current ancestor pathnames still name the same directories after concurrent rename. Post-read chain revalidation, mutation/replacement races and lifecycle locking remain further requirements before runtime admission.

## Tests first

- [x] Add fail-closed seam with no I/O or runtime wiring.
- [x] Add 24 cases using real temporary files, independent canonical signing, read-only open guards, preserved capability probes, symlink/FIFO rejection, size bounds and descriptor cleanup.
- [x] Observe both positive-file status assertions and the read-triggered expiry oracle RED on c94d9be, job 118309305597.
- [x] Implement only this reader after intended RED, then verify all 24 cases on e5588a0.
- [ ] Add mutation/replacement and ancestor-path revalidation tests before combining with lifecycle locking or runtime admission.

POSIX-specific cases require supported descriptor APIs and flags. Capability-negative cases still verify fail-closed behavior before any open. Synthetic test keys are deterministic fixture bytes, not live credentials. The reader never invokes legacy key creation/loaders, Docker, SQL, HTTP, coordinator or CLI; the approved outage remains disabled.

## Minimal reader after observed RED

The 24 reader tests and 66 parser cases are unchanged. Initial nofollow component traversal and bounded regular-file reads are followed by both descriptor/name snapshot checks after both reads. Every acquired fd receives one reverse-order close attempt, including after deadline expiry; ambiguous interrupted closes are not retried. Ordinary cleanup errors prevent SIGNED_METADATA, and pending interrupts propagate after remaining cleanup attempts. Own-source initial GREEN is verified. Additional mutation/interrupt/close-failure oracles and post-read ancestor checks remain required before any lock or runtime wiring. This is neither an atomic file-pair snapshot nor authenticated key provenance.

## Extended tests-first boundary

The next 46-case cohort preserves the original 24, adds four post-key-EOF leaf replacement/metadata checks and twelve interrupt/ordinary-close cases, then six ancestor rename/symlink cases expected to expose the missing post-read chain check. Their execution is pending. Close interrupts cover release-then-interrupt; ordinary OSError covers both released and intentionally unreleased outcomes. Assertions distinguish one cleanup attempt from actual release, and test-only cleanup handles explicitly unreleased fixture descriptors. No atomic namespace snapshot, lock, key provenance or runtime admission is claimed.
