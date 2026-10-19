# Existing signed-owner file boundary

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

The pure supplied-byte parser has 66 verified cases. This next slice introduces only an unavailable read_signed_owner_v11_from_state seam and 24 deterministic existing-file tests. It performs no filesystem work until implementation after observed RED.

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
- [ ] Observe two positive-file status assertions and the read-triggered expiry oracle RED, not setup failures.
- [ ] Implement only this reader after intended RED, then verify all cases on its own source.
- [ ] Add mutation/replacement and ancestor-path revalidation tests before combining with lifecycle locking or runtime admission.

POSIX-specific cases require supported descriptor APIs and flags. Capability-negative cases still verify fail-closed behavior before any open. Synthetic test keys are deterministic fixture bytes, not live credentials. The reader never invokes legacy key creation/loaders, Docker, SQL, HTTP, coordinator or CLI; the approved outage remains disabled.
